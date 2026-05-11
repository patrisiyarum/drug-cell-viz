"""HRDetect endpoints.

POST /api/hrdetect/score-vcf  — accepts a VCF upload, runs the demo
                               signature-extraction stub, returns the
                               HRDetect probability + label.
POST /api/hrdetect/score-features — accepts the six WGS-derived
                               feature values directly, runs the
                               logistic regression, returns the score.
                               Use this path when a clinician /
                               research project has already extracted
                               signatures.

Both paths return identical response shape so the frontend tile can
render either source the same way.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api.agents import hrdetect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hrdetect", tags=["hrdetect"])


class FeaturesIn(BaseModel):
    hrd_loh: float = Field(..., ge=0)
    e_del_mh_prop: float = Field(..., ge=0, le=1)
    sbs3: float = Field(..., ge=0, le=1)
    sbs8: float = Field(..., ge=0, le=1)
    rs3: float = Field(..., ge=0, le=1)
    rs5: float = Field(..., ge=0, le=1)


class HRDetectFeaturesOut(BaseModel):
    hrd_loh: float
    e_del_mh_prop: float
    sbs3: float
    sbs8: float
    rs3: float
    rs5: float


class HRDetectResponse(BaseModel):
    probability: float
    label: str
    features: HRDetectFeaturesOut
    feature_source: str
    intercept: float
    coefficients: dict[str, float]
    duration_ms: int
    caveats: list[str]


def _to_response(result: hrdetect.HRDetectResult) -> HRDetectResponse:
    d = hrdetect.result_to_dict(result)
    return HRDetectResponse(**d)


@router.post("/score-vcf", response_model=HRDetectResponse)
async def score_from_vcf(file: UploadFile = File(...)) -> HRDetectResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="no filename on upload")
    suffix = ".vcf.gz" if file.filename.endswith(".gz") else ".vcf"

    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = Path(tmp.name)
    try:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            tmp.write(chunk)
        tmp.close()
        try:
            result = hrdetect.run_from_vcf(tmp_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("hrdetect run_from_vcf failed")
            raise HTTPException(500, f"HRDetect failed: {exc}") from exc
        return _to_response(result)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


@router.post("/score-features", response_model=HRDetectResponse)
async def score_from_features(body: FeaturesIn) -> HRDetectResponse:
    feats = hrdetect.SignatureFeatures(**body.model_dump())
    result = hrdetect.run_from_features(feats)
    return _to_response(result)
