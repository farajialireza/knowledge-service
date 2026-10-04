"""Application configuration, loaded from environment variables / .env file."""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Values are read from process environment variables, falling back to the
    local `.env` file (which is never committed — see `.env.example`).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # tolerate unrelated variables in shared .env files
    )

    # Application
    app_name: str = "ai-knowledge-service"
    environment: str = "development"
    log_level: str = "INFO"

    # PostgreSQL (schema/tables are managed externally; this service only
    # connects — it must never create or alter database objects).
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "postgres"  # database name; `ai_assistant` is the SCHEMA
    db_user: str = "postgres"
    db_password: str = ""
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_connect_timeout: float = 5.0

    # Uploads / storage
    storage_dir: str = "data/uploads"  # original files, content-addressed by SHA-256
    max_upload_mb: int = 50

    # Chunking (character-based, ≈4 chars/token; validated below)
    chunk_size_chars: int = 2000
    chunk_overlap_chars: int = 200

    # Embeddings — text-embedding-3-small natively outputs 1536 dimensions,
    # matching the document_chunks.embedding VECTOR(1536) column.
    openai_api_key: str = ""
    openai_base_url: str | None = None  # set for a proxy/gateway endpoint
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 64

    # Max concurrent ingestion jobs (bounds DB pool and OpenAI rate usage)
    ingestion_max_concurrent: int = 2

    @model_validator(mode="after")
    def _check_chunking(self) -> "Settings":
        if not 0 <= self.chunk_overlap_chars < self.chunk_size_chars:
            raise ValueError("CHUNK_OVERLAP_CHARS must be >= 0 and < CHUNK_SIZE_CHARS")
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def db_connect_kwargs(self) -> dict:
        """Connection parameters for psycopg.

        Passed as keyword arguments (instead of a conninfo/DSN string) so
        credentials containing spaces or special characters need no escaping.
        """
        return {
            "host": self.db_host,
            "port": self.db_port,
            "dbname": self.db_name,
            "user": self.db_user,
            "password": self.db_password,
            "connect_timeout": int(self.db_connect_timeout),
        }


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so configuration is parsed only once per process."""
    return Settings()
