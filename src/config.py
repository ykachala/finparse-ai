from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    port: int = 8000
    environment: str = "development"

    # Database
    database_url: str  # postgresql+asyncpg://...
    sync_database_url: str  # postgresql://... (for Alembic/Celery)

    # Redis
    redis_url: str

    # Anthropic
    anthropic_api_key: str

    # AWS
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_s3_bucket: str
    aws_region: str = "eu-west-1"

    # Auth
    api_key_salt: str  # hex string for hashing API keys

    # Processing limits
    max_file_size_mb: int = 20
    max_batch_size: int = 50
    sync_parse_timeout_seconds: int = 30


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
