from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_env: str = "development"

    database_url: str
    database_url_readonly: str

    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "llama3"
    ollama_embedding_model: str = "nomic-embed-text"

    upload_dir: Path = ROOT / "storage" / "uploads"
    max_upload_mb: int = 25

    cors_origins: str = "http://localhost:5173"

    # Cosine distance above this means "not relevant enough" (SEC-002).
    rag_max_distance: float = 0.6
    rag_top_k: int = 4
    sql_timeout_ms: int = 5000

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        p = self.upload_dir if self.upload_dir.is_absolute() else ROOT / self.upload_dir
        return p.resolve()


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.upload_path.mkdir(parents=True, exist_ok=True)
    return s
