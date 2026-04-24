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
    )
