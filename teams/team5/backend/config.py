"""Application settings loaded from environment variables with validation."""

from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    ANTHROPIC_API_KEY: str = ""
    LLM_PROVIDER: Literal["anthropic", "ollama", "openrouter"] = "openrouter"
    LLM_MODEL: str = "openai/gpt-4o-mini"
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # OpenRouter
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Embeddings
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"

    # Ports
    BACKEND_PORT: int = 8001
    FRONTEND_PORT: int = 3002

    # Public API URL (used by frontend)
    NEXT_PUBLIC_API_URL: str = "https://iknl.datameesters.nl"

    # Storage paths
    CHROMADB_PATH: str = "data/chromadb"
    FEEDBACK_DB_PATH: str = "data/feedback.db"
    KANKER_NL_JSON_PATH: str = "data/kanker_nl_pages_all.json"
    PUBLICATIONS_DIR: str = "data/reports"
    SCIENTIFIC_PUBLICATIONS_DIR: str = "data/scientific_publications"
    SITEMAP_PATH: str = "data/sitemap.json"

    # External APIs
    NKR_API_BASE_URL: str = "https://api.nkr-cijfers.iknl.nl/api"
    CANCER_ATLAS_URL: str = "https://kankeratlas.iknl.nl"
    CANCER_ATLAS_STRAPI_URL: str = "https://iknl-atlas-strapi-prod.azurewebsites.net"

    @field_validator("BACKEND_PORT", "FRONTEND_PORT")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1024 <= v <= 65535:
            raise ValueError(f"Port must be between 1024 and 65535, got {v}")
        return v

    @field_validator("LLM_MODEL")
    @classmethod
    def validate_model(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("LLM_MODEL cannot be empty")
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
