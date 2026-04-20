"""Blob storage abstraction.

In development we persist to the local filesystem and serve bytes through the
API's own `/blobs/...` static mount. In production `storage_backend=r2` would
swap in Cloudflare R2 with signed URLs. The caller never cares which.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from api.config import settings


def _local_path(key: str) -> Path:
    # Prevent escaping the root. Keys are always server-generated, but defense in depth.
    safe = key.lstrip("/").replace("..", "_")
    return settings.local_storage_root / safe


async def put(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Store `data` at `key`. Returns a URL the frontend can fetch."""
    if settings.storage_backend == "local":
        path = _local_path(key)
        await asyncio.to_thread(_write_local, path, data)
        return f"{settings.public_base_url.rstrip('/')}/blobs/{key.lstrip('/')}"
    raise NotImplementedError(f"storage backend {settings.storage_backend!r} not implemented")


async def get(key: str) -> bytes | None:
    if settings.storage_backend == "local":
        path = _local_path(key)
        if not path.exists():
            return None
        return await asyncio.to_thread(path.read_bytes)
    raise NotImplementedError(f"storage backend {settings.storage_backend!r} not implemented")


async def exists(key: str) -> bool:
    if settings.storage_backend == "local":
        return _local_path(key).exists()
    raise NotImplementedError(f"storage backend {settings.storage_backend!r} not implemented")


def _write_local(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
