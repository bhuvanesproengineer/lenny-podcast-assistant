import os
from pathlib import Path
from dotenv import load_dotenv

# Locate and load .env file from project root or backend directory
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

class Settings:
    # Application & Server Settings
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info").lower()
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000")

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.CORS_ORIGINS:
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    # Dual Model Layer Settings
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower().strip()
    FALLBACK_TO_LOCAL: bool = os.getenv("FALLBACK_TO_LOCAL", "true").lower() in ("true", "1", "yes")
    
    # Local LLM (Ollama)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_DEFAULT_MODEL: str = os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2:3b")
    
    # Cloud Model Provider
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    CLOUD_MODEL: str = os.getenv("CLOUD_MODEL", "anthropic/claude-sonnet-4")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "")
    
    # Groq Cloud Provider
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", os.getenv("MODEL", "openai/gpt-oss-20b"))
    
    # Gemini Cloud Embeddings
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GEMINI_EMBEDDING_MODEL: str = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

    # Cloud Token Budget & TPM Protection (Cloud Mode Only)
    CLOUD_TOP_K: int = int(os.getenv("CLOUD_TOP_K", "4"))
    CLOUD_MAX_CONTEXT_TOKENS: int = int(os.getenv("CLOUD_MAX_CONTEXT_TOKENS", "1800"))
    CLOUD_TPM_LIMIT: int = int(os.getenv("CLOUD_TPM_LIMIT", "20000"))

    # RAG & Embeddings Configuration
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "ollama").lower().strip()
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "768"))
    EMBEDDING_BATCH_SIZE: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "50"))
    SIMILARITY_TOP_K: int = int(os.getenv("SIMILARITY_TOP_K", "6"))
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.50"))
    RAG_MIN_RELEVANT_CHUNKS: int = int(os.getenv("RAG_MIN_RELEVANT_CHUNKS", "2"))

settings = Settings()
