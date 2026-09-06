from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.health import router as health_router
from app.api.sessions import router as sessions_router
from app.api.chat import router as chat_router
from app.api.export import router as export_router
from app.api.settings import router as settings_router
from app.database import init_db, engine
from app.config import settings

import asyncio
from app.agent.tools import set_main_event_loop

async def run_startup_health_check():
    """
    Startup validation & diagnostics:
    1. Verifies embedding model exists on Google GenAI API when in Cloud mode.
    2. Generates test embedding for 'hello world' before enabling retrieval.
    3. Logs Selected Embedding Provider and Selected Embedding Model.
    4. Prints complete diagnostic summary.
    """
    from app.providers.provider_factory import get_active_provider_name, get_provider
    from app.rag.embedding_router import (
        get_active_embedding_provider,
        get_embedding_info,
        get_embedding_generator,
        GeminiEmbeddingGenerator,
    )
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    llm_provider = get_active_provider_name()
    try:
        prov = get_provider(llm_provider, fallback_on_error=False)
        chat_model = getattr(prov, "model_name", getattr(prov, "model", "unknown"))
    except Exception:
        chat_model = getattr(settings, "GROQ_MODEL", "openai/gpt-oss-20b") if llm_provider in ("cloud", "groq") else getattr(settings, "OLLAMA_DEFAULT_MODEL", "llama3.2:3b")

    emb_info = get_embedding_info()
    emb_provider = emb_info["provider"]
    emb_model = emb_info["model"]
    vector_table = emb_info["table"]

    # Requirement 4 & 6: Startup Validation
    print(
        f"Selected Embedding Provider: {emb_provider}\n"
        f"Selected Embedding Model: {emb_model}",
        flush=True
    )

    model_verification_status = "Skipped (Local Ollama)"
    if emb_provider == "gemini":
        try:
            gemini_gen = get_embedding_generator("gemini")
            if isinstance(gemini_gen, GeminiEmbeddingGenerator):
                verif = await gemini_gen.verify_embedding_model_exists()
                if verif.get("exists") and verif.get("tested"):
                    model_verification_status = f"Verified & Tested (dim={verif.get('dimension')})"
                elif verif.get("exists"):
                    model_verification_status = f"Verified Model Exists ({verif.get('model')})"
                else:
                    model_verification_status = f"FAILED: {verif.get('error')}"
        except Exception as exc:
            model_verification_status = f"Error during verification: {exc}"

    chunk_count = 0
    try:
        async with AsyncSessionLocal() as session:
            count_query = text(f"SELECT COUNT(*) FROM {vector_table}")
            res = await session.execute(count_query)
            chunk_count = res.scalar() or 0
    except Exception as exc:
        chunk_count = f"Error: {exc}"

    print(
        f"\n============================================================\n"
        f"STARTUP HEALTH CHECK\n"
        f"============================================================\n"
        f"Current LLM Provider:          {llm_provider}\n"
        f"Current Embedding Provider:    {emb_provider}\n"
        f"Current Chat Model:            {chat_model}\n"
        f"Current Embedding Model:       {emb_model}\n"
        f"Current Vector Table:          {vector_table}\n"
        f"Model Verification Status:     {model_verification_status}\n"
        f"Chunk Count In Selected Table: {chunk_count}\n"
        f"============================================================\n",
        flush=True
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager:
    Automatically creates database tables and extensions on startup.
    Disposes database engine connections on shutdown.
    """
    # Startup: Set active event loop for thread-safe agent tool scheduling
    try:
        set_main_event_loop(asyncio.get_running_loop())
    except RuntimeError:
        pass

    # Startup: Ensure tables and pgvector extension are created
    await init_db()

    # Startup Health Check
    await run_startup_health_check()

    yield
    # Shutdown: Cleanly close connection pool
    set_main_event_loop(None)
    await engine.dispose()

app = FastAPI(
    title="Lenny Growth Assistant API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach API routers
app.include_router(health_router)
app.include_router(sessions_router)
app.include_router(chat_router)
app.include_router(export_router)
app.include_router(settings_router)
