from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_port: int = 8000
    database_url: str = "postgresql+asyncpg://drug:drug@postgres:5432/drug"
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"

    # Storage: in dev we use the local filesystem. In prod these point at R2.
    storage_backend: str = "local"  # "local" | "r2"
    local_storage_root: Path = Path("./data/blobs")
    public_base_url: str = "http://localhost:8000"
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
