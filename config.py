"""
Configuration and environment settings for production deployment.
All sensitive data loaded from environment variables.
"""

from typing import List, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with validation"""

    # =====================
    # Application
    # =====================
    APP_NAME: str = "Job Automation API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"  # 'development', 'staging', 'production'
    DEBUG: bool = False

    # =====================
    # API Server
    # =====================
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_PREFIX: str = "/api"

    # =====================
    # Database
    # =====================
    DATABASE_URL: str = "sqlite:///./job_automation.db"  # Override in .env
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_RECYCLE: int = 3600
    DATABASE_ECHO: bool = False  # Set True for SQL logging

    # =====================
    # Cache (Redis)
    # =====================
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None
    REDIS_CACHE_TTL: int = 86400  # 24 hours
    REDIS_SESSION_TTL: int = 604800  # 7 days

    # =====================
    # LLM (Ollama - Local Models)
    # =====================
    LLM_PROVIDER: str = "ollama"  # 'ollama' or 'anthropic'
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Primary model — used for tailored resume + cover letter generation
    LLM_MODEL: str = "deepseek-r1:8b"
    # Fast model — used for bulk job scoring / embeddings pre-filter
    FAST_LLM_MODEL: str = "qwen3:8b"
    # Embedding model — used for semantic pre-filtering
    EMBEDDING_MODEL: str = "nomic-embed-text"

    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.4
    LLM_TIMEOUT: int = 120  # seconds (local models may be slower)

    # Embedding pre-filter: top N jobs passed to the LLM for full scoring
    EMBEDDING_TOP_N: int = 30

    # Anthropic (optional fallback — use set_credential('anthropic_api_key', ...))
    ANTHROPIC_API_KEY: Optional[str] = None

    # =====================
    # CORS
    # =====================
    CORS_ORIGINS: List[str] = [
        "http://localhost:8501",  # Streamlit dev
        "http://localhost:3000",  # React dev
    ]

    # =====================
    # Rate Limiting
    # =====================
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60  # seconds

    # =====================
    # Logging
    # =====================
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # 'json' or 'text'
    SENTRY_DSN: Optional[str] = None

    # =====================
    # Job Discovery
    # =====================
    JOB_SEARCH_TIMEOUT: int = 30  # seconds
    JOB_SEARCH_RETRIES: int = 3
    JOB_CACHE_TTL: int = 86400  # 24 hours
    JOB_DEDUP_DAYS: int = 7  # Avoid duplicate searches

    # =====================
    # Application Submission
    # =====================
    APPLICATION_RETRY_ATTEMPTS: int = 3
    APPLICATION_RETRY_DELAY: int = 5  # seconds
    CAPTCHA_WAIT_TIMEOUT: int = 300  # seconds (5 minutes)
    HEADLESS_BROWSER: bool = True
    BROWSER_TIMEOUT: int = 30  # seconds
    BROWSER_SLOWMO: int = 0  # milliseconds between actions

    # =====================
    # Feature Flags
    # =====================
    ENABLE_LINKEDIN_APPLY: bool = True
    ENABLE_NAUKRI_APPLY: bool = True
    ENABLE_GENERIC_APPLY: bool = True
    ENABLE_JOB_MATCHING: bool = True
    ENABLE_RESUME_TAILORING: bool = True

    # =====================
    # Data Retention
    # =====================
    KEEP_APPLICATION_HISTORY_DAYS: int = 730  # 2 years
    KEEP_JOB_CACHE_DAYS: int = 30
    KEEP_RESUME_VERSIONS: int = 10

    class Config:
        """Pydantic config"""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        # Allow extra fields from env
        extra = "allow"

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT == "development"

    @property
    def database_url_safe(self) -> str:
        """Return database URL with password masked for logging"""
        if "://" not in self.DATABASE_URL:
            return self.DATABASE_URL
        scheme, rest = self.DATABASE_URL.split("://", 1)
        if "@" in rest:
            _, host = rest.split("@", 1)
            return f"{scheme}://***@{host}"
        return self.DATABASE_URL


# Create global settings instance
settings = Settings()


# =====================
# Validation
# =====================

if settings.is_production:
    """Production safety checks"""
    if settings.LLM_PROVIDER == "anthropic":
        assert (
            settings.ANTHROPIC_API_KEY
        ), "ANTHROPIC_API_KEY must be set when LLM_PROVIDER=anthropic"
    assert (
        "sqlite" not in settings.DATABASE_URL
    ), "SQLite not allowed in production (use PostgreSQL)"
    assert settings.DEBUG is False, "DEBUG must be False in production"
    assert (
        "localhost" not in settings.DATABASE_URL
    ), "Database must not be localhost in production"

# Development defaults
if settings.is_development:
    settings.DEBUG = True
    settings.LOG_LEVEL = "DEBUG"
    settings.DATABASE_ECHO = False  # Can enable for SQL debugging

__all__ = ["settings", "Settings"]
