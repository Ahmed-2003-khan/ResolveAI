from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    app_secret_key: str = "change-me-in-production"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://resolveai:resolveai@localhost:5432/resolveai"
    postgres_user: str = "resolveai"
    postgres_password: str = "resolveai"
    postgres_db: str = "resolveai"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # OpenAI
    openai_api_key: str = ""
    openai_default_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # Groq
    groq_api_key: str = ""
    groq_default_model: str = "llama-3.1-8b-instant"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "llama3:8b"

    # Twilio (WhatsApp)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"

    # AWS (Email)
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-south-1"
    ses_from_email: str = "support@example.com"

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    # Admin UI
    admin_username: str = "admin"
    admin_password: str = "change-me"

    # Semantic cache
    semantic_cache_similarity_threshold: float = 0.97
    semantic_cache_ttl_hours: int = 24

    # LLM circuit breaker
    llm_circuit_breaker_failures: int = 3
    llm_circuit_breaker_window_seconds: int = 60
    llm_circuit_breaker_cooldown_seconds: int = 300

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
