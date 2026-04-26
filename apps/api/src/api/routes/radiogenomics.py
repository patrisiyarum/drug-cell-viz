"""Radiogenomics upload endpoint.

POST /api/radiogenomics/upload accepts a CT scan (DICOM zip or NIfTI file),
runs the real preprocessing pipeline, and returns an HRD probability
prediction + metadata + caveats. Until a trained model is wired up, the
prediction is an explicit `model_not_trained` placeholder with a clear
disclaimer the UI surfaces prominently.

Endpoint contract designed so that when the hrd-radiogenomics research repo
ships trained weights, dropping the checkpoint in and calling
`services.radiogenomics.set_model_weights(...)` at startup flips the
endpoint to real predictions without any route-level changes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api.services import radiogenomics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/radiogenomics", tags=["radiogenomics"])


# Hard cap on upload size — a single CT series is typically 50-500 MB; we cap
# at 1 GB to reject accidental whole-body studies or malformed zips.
MAX_UPLOAD_BYTES = 1_000_000_000


class VolumeMetadataOut(BaseModel):
    modality: str
    original_shape: tuple[int, int, int]
    original_spacing_mm: tuple[float, float, float]
    target_shape: tuple[int, int, int]
    hu_window: tuple[float, float]


class RadiogenomicsResponse(BaseModel):
    metadata: VolumeMetadataOut
    hrd_probability: float = Field(..., ge=0.0, le=1.0)
    label: str
    confidence: str
    caveats: list[str]
    # Signals the UI uses to decide whether to render the placeholder banner
    # or a real prediction card.
    model_available: bool
    # URL of the resolved 3D NIfTI volume the backend assembled from the
    # upload. Present whenever we successfully built a volume — the
    # frontend's slideshow viewer (niivue) renders this URL so the user
    # sees the same scan the model just scored, even if they uploaded a
    # .tcia manifest or a DICOM zip (formats niivue can't read directly).
    volume_url: str | None = None


@router.post("/upload", response_model=RadiogenomicsResponse, status_code=201)
async def upload_ct_scan(file: UploadFile = File(...)) -> RadiogenomicsResponse:
    if file.filename is None:
        raise HTTPException(status_code=400, detail="upload missing filename")

    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"upload exceeds {MAX_UPLOAD_BYTES // 1_000_000} MB cap; "
                "a single CT series should fit well under this"
            ),
        )

    try:
        volume, metadata = radiogenomics.load_volume(raw, file.filename)
    except radiogenomics.RadiogenomicsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("CT upload load_volume failed")
        raise HTTPException(status_code=500, detail=f"internal load error: {exc}") from exc

    # Persist the resolved 3D volume as a NIfTI in blob storage so the
    # frontend's niivue viewer can render the same scan the model
    # consumed. Filename is the SHA-256 hash of the raw upload + first
    # 8 chars truncated, so re-uploading the same file is cached and
    # different uploads don't collide.
    volume_url: str | None = None
    try:
        volume_url = _persist_volume_as_nifti(volume, metadata, raw)
    except Exception:  # noqa: BLE001
        logger.exception("could not persist resolved volume as NIfTI; viewer will fall back")

    try:
        preprocessed = radiogenomics.preprocess(volume, metadata)
    except Exception as exc:  # noqa: BLE001
        logger.exception("CT upload preprocess failed")
        raise HTTPException(status_code=500, detail=f"preprocess error: {exc}") from exc

    prediction = radiogenomics.infer_hrd(preprocessed, metadata)

    return RadiogenomicsResponse(
        metadata=VolumeMetadataOut(
            modality=prediction.metadata.modality,
            original_shape=prediction.metadata.original_shape,
            original_spacing_mm=prediction.metadata.original_spacing_mm,
            target_shape=prediction.metadata.target_shape,
            hu_window=prediction.metadata.hu_window,
        ),
        hrd_probability=prediction.hrd_probability,
        label=prediction.label,
        confidence=prediction.confidence,
        caveats=prediction.caveats,
        model_available=prediction.label != "model_not_trained",
        volume_url=volume_url,
    )


def _persist_volume_as_nifti(
    volume,  # np.ndarray (Z, Y, X)
    metadata: "radiogenomics.VolumeMetadata",
    raw: bytes,
) -> str:
    """Write the assembled 3D volume to /blobs/radiogenomics/<hash>.nii.gz
    so the frontend slideshow viewer can render the same scan the model
    just scored. Returns a public URL the frontend can fetch."""
    import hashlib
    import nibabel as nib
    import numpy as np

    from api.config import settings

    # Hash-derived filename → idempotent across re-uploads.
    digest = hashlib.sha256(raw).hexdigest()[:16]
    out_dir = settings.local_storage_root / "radiogenomics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{digest}.nii.gz"

    if not out_path.exists():
        # Volume comes in (Z, Y, X); NIfTI canonical layout is (X, Y, Z).
        vol_xyz = np.transpose(volume.astype(np.int16), (2, 1, 0))
        sz, sy, sx = metadata.original_spacing_mm
        affine = np.diag([sx, sy, sz, 1.0]).astype(np.float32)
        nib.save(nib.Nifti1Image(vol_xyz, affine), str(out_path))

    return f"{settings.public_base_url.rstrip('/')}/blobs/radiogenomics/{digest}.nii.gz"
