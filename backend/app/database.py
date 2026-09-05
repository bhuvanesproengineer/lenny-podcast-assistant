from typing import AsyncGenerator
from urllib.parse import urlparse, parse_qs, urlunparse
from sqlalchemy import text
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import asyncpg
from app.config import settings

Base = declarative_base()

def _get_connection_params(database_url: str):
    """
    Parses DATABASE_URL and extracts a clean DSN and SSL context suitable for asyncpg / SQLAlchemy async.
    Handles Neon and cloud PostgreSQL parameters (e.g. sslmode=require, channel_binding).
    """
    parsed = urlparse(database_url)
    scheme = "postgresql"
    query_params = parse_qs(parsed.query)
    
    ssl_mode = query_params.get("sslmode", [""])[0]
    ssl_param = query_params.get("ssl", [""])[0]
    requires_ssl = (
        ssl_mode in ("require", "verify-ca", "verify-full") 
        or ssl_param in ("true", "require", "1")
        or "neon.tech" in (parsed.hostname or "")
    )

    clean_dsn = urlunparse((
        scheme,
        parsed.netloc,
        parsed.path,
        "",
        "",
        ""
    ))
    
    ssl_context = "require" if requires_ssl else None
    return clean_dsn, ssl_context

# Prepare SQLAlchemy Async Engine
clean_dsn, _ssl_context = _get_connection_params(settings.DATABASE_URL)
async_db_url = clean_dsn.replace("postgresql://", "postgresql+asyncpg://")

connect_args = {"ssl": _ssl_context} if _ssl_context else {}

engine = create_async_engine(
    async_db_url,
    connect_args=connect_args,
    echo=False,
    pool_pre_ping=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency generator providing an asynchronous SQLAlchemy database session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db() -> None:
    """
    Initializes PostgreSQL tables and ensures the pgvector extension is created.
    """
    # Import models to ensure they are registered with Base.metadata
    from app.models import db_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)

async def check_db_connection() -> tuple[bool, str | None]:
    """
    Verifies PostgreSQL connectivity asynchronously.
    Returns (True, None) on success or (False, error_message) on failure.
    """
    if not settings.DATABASE_URL:
        return False, "DATABASE_URL is not set in the environment"

    try:
        clean_dsn, ssl_context = _get_connection_params(settings.DATABASE_URL)
        conn = await asyncpg.connect(
            clean_dsn,
            ssl=ssl_context,
            timeout=5.0
        )
        try:
            result = await conn.fetchval("SELECT 1;")
            if result == 1:
                return True, None
            return False, "Database responded with unexpected result"
        finally:
            await conn.close()
    except Exception as exc:
        return False, str(exc)
