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
