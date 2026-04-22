"""Runtime inference for the BRCA2 DBD classifier.

v0 baseline — trained on Huang et al. 2025 SGE data for 4,404 BRCA2 DBD
missense variants. AUROC 0.842 on the held-out 20%. Uses the same feature
pipeline as BRCA1 (with BRCA1 domain one-hots all zero for BRCA2 — see
train_brca2.py caveat).

Unlike the BRCA1 model, there's no ensemble with AlphaMissense yet and no
conformal calibration. Returning only the model's binary probability plus the
standard metadata.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

import xgboost as xgb

from api.ml.features import featurize_one
from api.ml.infer import (
    VariantParseError,
    infer_consequence,
    parse_hgvs_protein,
)

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
MODEL_PATH = HERE / "models" / "brca2_xgb_v1.json"
META_PATH = HERE / "models" / "brca2_xgb_v1_metadata.json"

# Huang et al. 2025 covers the BRCA2 DNA-binding domain (residues 2479-3216).
BRCA2_ASSAYED_RANGE = (2479, 3216)


@lru_cache(maxsize=1)
def _load_model() -> xgb.XGBClassifier:
    if not MODEL_PATH.exists():
        raise RuntimeError(
            f"BRCA2 classifier not trained yet. Run: uv run python -m api.ml.train_brca2 "
            f"(expected model at {MODEL_PATH})"
        )
    clf = xgb.XGBClassifier()
    clf.load_model(str(MODEL_PATH))
    return clf


@lru_cache(maxsize=1)
def load_metadata() -> dict:
    if not META_PATH.exists():
        return {}
    return json.loads(META_PATH.read_text())


def _in_assayed_region(pos: int) -> bool:
    lo, hi = BRCA2_ASSAYED_RANGE
    return lo <= pos <= hi


ClassificationLabel = Literal["likely_pathogenic", "likely_benign", "uncertain"]


def classify(ref_aa: str, pos: int, alt_aa: str) -> dict:
    """Predict pathogenicity for a BRCA2 DBD missense variant."""
    clf = _load_model()
    consequence = infer_consequence(ref_aa, alt_aa)
    x = featurize_one(float(pos), ref_aa, alt_aa, consequence).reshape(1, -1)
    p = float(clf.predict_proba(x)[0, 1])

    label: ClassificationLabel
    if p >= 0.70:
        label = "likely_pathogenic"
    elif p <= 0.30:
        label = "likely_benign"
    else:
        label = "uncertain"

    distance = abs(p - 0.5)
    confidence = "high" if distance >= 0.35 else "moderate" if distance >= 0.20 else "low"

    return {
        "probability_pathogenic": round(p, 3),
        "label": label,
        "consequence": consequence,
        "in_assayed_region": _in_assayed_region(pos),
        "confidence": confidence,
    }


# Re-export parse_hgvs_protein + VariantParseError so callers only import one module.
__all__ = ["parse_hgvs_protein", "VariantParseError", "classify", "load_metadata"]
