"""Runtime inference for the BRCA1 variant-effect classifier.

Two models are loaded at startup:
  - XGBoost v1 (on engineered features — see features.py)
  - Logistic ensemble v1 combining XGB + AlphaMissense pathogenicity scores

At predict time we return the ensemble probability plus a split-conformal
prediction set at 80% coverage. When AlphaMissense doesn't cover a variant
(synonymous / nonsense / outside its table), we impute with the training
mean so the ensemble still fires, and flag the response accordingly.
"""

from __future__ import annotations

import json
import logging
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import xgboost as xgb

from api.ml import alphamissense as am
from api.ml.features import DOMAINS, featurize_one

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
MODEL_PATH = HERE / "models" / "brca1_xgb_v1.json"
ENSEMBLE_PATH = HERE / "models" / "brca1_ensemble_v1.json"
META_PATH = HERE / "models" / "brca1_xgb_v1_metadata.json"

# 1-letter and 3-letter amino acid codes.
THREE_TO_ONE = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
    "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H", "Ile": "I",
    "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
    "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
    "Ter": "*", "*": "*",
}
ONE_TO_ONE = {c: c for c in "ACDEFGHIKLMNPQRSTVWY"}
ONE_TO_ONE["*"] = "*"


class VariantParseError(ValueError):
    pass


def parse_hgvs_protein(text: str) -> tuple[str, int, str]:
    s = text.strip()
    if s.startswith("p."):
        s = s[2:]
    three = re.fullmatch(r"([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2}|\*|Ter)", s)
    if three:
        ref3, pos, alt3 = three.groups()
        if ref3 not in THREE_TO_ONE or alt3 not in THREE_TO_ONE:
            raise VariantParseError(f"unrecognized amino acid code in {text!r}")
        return THREE_TO_ONE[ref3], int(pos), THREE_TO_ONE[alt3]
    one = re.fullmatch(r"([A-Z])(\d+)([A-Z*])", s)
    if one:
        ref1, pos, alt1 = one.groups()
        if ref1 not in ONE_TO_ONE or alt1 not in ONE_TO_ONE:
            raise VariantParseError(f"unrecognized amino acid code in {text!r}")
        return ref1, int(pos), alt1
    raise VariantParseError(
        f"couldn't parse {text!r} as an HGVS protein variant"
    )


def infer_consequence(ref: str, alt: str) -> str:
    if alt == "*":
        return "Nonsense"
    if ref == alt:
        return "Synonymous"
    return "Missense"


@lru_cache(maxsize=1)
def _load_xgb() -> xgb.XGBClassifier:
    if not MODEL_PATH.exists():
        raise RuntimeError(f"BRCA1 classifier not trained yet (expected at {MODEL_PATH})")
    clf = xgb.XGBClassifier()
    clf.load_model(str(MODEL_PATH))
    return clf


@lru_cache(maxsize=1)
def _load_ensemble() -> dict:
    if not ENSEMBLE_PATH.exists():
        return {}
    return json.loads(ENSEMBLE_PATH.read_text())


@lru_cache(maxsize=1)
def load_metadata() -> dict:
    if not META_PATH.exists():
        return {}
    return json.loads(META_PATH.read_text())


def _domain_for(pos: int) -> str:
    for name, (lo, hi) in DOMAINS.items():
        if lo <= pos <= hi:
            return name
    return "outside_assayed_domains"


def _in_assayed_region(pos: int) -> bool:
    return _domain_for(pos) in {"RING", "CoiledCoil", "BRCT1", "BRCT_linker", "BRCT2"}


ClassificationLabel = Literal["likely_loss_of_function", "likely_functional", "uncertain"]


def _ensemble_proba(xgb_p: float, am_score: float | None) -> tuple[float, float]:
    """Return (ensemble probability, AlphaMissense value used including imputation)."""
    ens = _load_ensemble()
    if not ens:
        # Ensemble not trained — fall back to XGB prob alone.
        return xgb_p, float("nan")
    w_xgb, w_am = ens["coef"]
    b = ens["intercept"]
    fill = ens.get("am_fill_value", 0.4)
    am_used = am_score if am_score is not None else float(fill)
    z = w_xgb * xgb_p + w_am * am_used + b
    return 1.0 / (1.0 + math.exp(-z)), am_used


def _conformal_prediction_set(p_lof: float, q: float) -> list[str]:
    """Split-conformal prediction set for coverage tied to threshold q.

    Include a class iff our uncertainty about it <= q. For binary LOF/FUNC
    with nonconformity score |y - p_LOF|:
      - include "LOF"  iff 1 - p_LOF <= q  i.e.  p_LOF >= 1 - q
      - include "FUNC" iff p_LOF        <= q
    """
    out: list[str] = []
    if 1 - p_lof <= q:
        out.append("loss_of_function")
    if p_lof <= q:
        out.append("functional")
    return out


def classify(ref_aa: str, pos: int, alt_aa: str) -> dict:
    """Predict HR functional effect for a BRCA1 variant.

    Returns ensemble probability, component scores, and an 80%-coverage
    conformal prediction set.
    """
    clf = _load_xgb()
    consequence = infer_consequence(ref_aa, alt_aa)
    x = featurize_one(float(pos), ref_aa, alt_aa, consequence).reshape(1, -1)
    xgb_p = float(clf.predict_proba(x)[0, 1])

    am_score: float | None = None
    am_class: str | None = None
    am_hit = am.lookup(ref_aa, pos, alt_aa)
    if am_hit is not None:
        am_score, am_class = float(am_hit[0]), am_hit[1]

    proba, am_used = _ensemble_proba(xgb_p, am_score)

    # Conformal at 80% coverage is the UI default.
    meta = load_metadata()
    q80 = float(
        meta.get("conformal", {}).get("thresholds", {}).get("0.8", 0.2)
    )
    set_at_80 = _conformal_prediction_set(proba, q80)
    # Interpretation of the singleton/both cases:
    if set_at_80 == ["loss_of_function"]:
        conformal_label = "loss_of_function"
    elif set_at_80 == ["functional"]:
        conformal_label = "functional"
    else:
        conformal_label = "uncertain"

    # Keep the qualitative label (backward-compat with the UI card) but compute
    # it from the ensemble probability.
    if proba >= 0.70:
        label: ClassificationLabel = "likely_loss_of_function"
    elif proba <= 0.30:
        label = "likely_functional"
    else:
        label = "uncertain"

    distance = abs(proba - 0.5)
    confidence = "high" if distance >= 0.35 else "moderate" if distance >= 0.20 else "low"

    return {
        "probability_loss_of_function": round(proba, 3),
        "label": label,
        "consequence": consequence,
        "domain": _domain_for(pos),
        "in_assayed_region": _in_assayed_region(pos),
        "confidence": confidence,
        "components": {
            "xgb_probability": round(xgb_p, 3),
            "alphamissense_score": round(float(am_score), 3) if am_score is not None else None,
            "alphamissense_class": am_class,
            "alphamissense_covered": am_score is not None,
            "alphamissense_value_used": round(float(am_used), 3) if not math.isnan(am_used) else None,
        },
        "conformal": {
            "coverage": 0.80,
            "threshold": q80,
            "prediction_set": set_at_80,
            "label": conformal_label,
        },
    }
