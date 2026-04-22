import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_port: int = 8000
    database_url: str = "postgresql+asyncpg://drug:drug@postgres:5432/drug"
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_db_url(cls, v: object) -> object:
        """Render (and Heroku-style providers) hand out `postgres://...` URLs.
        SQLAlchemy's async engine needs the driver-prefixed form. Promote
        automatically so the deploy just works without the user remembering.
        """
        if isinstance(v, str):
            if v.startswith("postgres://"):
                v = "postgresql+asyncpg://" + v[len("postgres://"):]
            elif v.startswith("postgresql://"):
                v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v

    # Storage: in dev we use the local filesystem. In prod these point at R2.
    storage_backend: str = "local"  # "local" | "r2"
    local_storage_root: Path = Path("./data/blobs")
    public_base_url: str = "http://localhost:8000"

    @field_validator("public_base_url", mode="before")
    @classmethod
    def _resolve_public_base_url(cls, v: object) -> object:
        """Fall back to Render's injected RENDER_EXTERNAL_URL when the value
        is missing or comes through unresolved from the Blueprint.

        render.yaml uses `value: $RENDER_EXTERNAL_URL` which is NOT expanded
        at Blueprint-parse time on Render (it's not Blueprint substitution
        syntax), so the API would otherwise read the literal string
        "$RENDER_EXTERNAL_URL" and hand broken PDB URLs to the frontend.
        RENDER_EXTERNAL_URL itself IS injected as a real env var on every
        Render service, so we can pick it up directly.
        """
        if isinstance(v, str) and (not v or v.startswith("$") or "localhost" in v):
            render_url = os.environ.get("RENDER_EXTERNAL_URL")
            if render_url:
                return render_url
        return v
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "drug-cell-viz"
    r2_endpoint: str = ""
    r2_public_url: str = ""

    # Modal (DiffDock). Off by default; Phase 1 stub handles docking.
    use_modal_docking: bool = False
    modal_app_name: str = "drug-cell-viz"
    modal_diffdock_fn: str = "dock_ligand"

    # JUMP-CP (Phase 3). A bundled JSON catalog is used by default; real index
    # lives in object storage once `scripts/download_jump_subset.py` has run.
    jump_faiss_index_key: str = "indices/jump-v1.faiss"
    jump_metadata_key: str = "indices/jump-v1-meta.parquet"

    # Rate limiting
    rate_limit_jobs_per_hour: int = 10


settings = Settings()
