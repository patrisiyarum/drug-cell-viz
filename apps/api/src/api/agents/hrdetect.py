"""HRDetect — published whole-genome HRD signature classifier (Davies 2017).

HRDetect is a logistic regression over six WGS-derived features:

    HRD-LOH index          (continuous, structural)
    e.del.mh.prop          (microhomology-mediated deletion fraction)
    SBS3                   (substitution signature 3 contribution)
    SBS8                   (substitution signature 8 contribution)
    RS3                    (rearrangement signature 3 contribution)
    RS5                    (rearrangement signature 5 contribution)

Reference: Davies et al., HRDetect is a predictor of BRCA1 and BRCA2
deficiency based on mutational signatures (Nat Med 2017),
supplementary table 6.

This module is honest about two things:

  1. The signature-extraction step is a STUB. Real signature
     extraction (SigProfiler / Signal / SigMA) needs whole-genome
     sequencing and substantial compute; clinical panels lack the
     mutation count to fit a signature mixture. A real production
     pipeline would route the VCF to a dedicated extraction service.
     We document the stub clearly and surface that in the response.

  2. The logistic regression coefficients applied here mirror the
     structure and signs reported in the supplementary materials but
     should be re-verified against the original paper before any
     non-demo use.

The score function is real arithmetic. Plug verified coefficients into
`HRDETECT_COEFFICIENTS` to get production output.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Logistic-regression coefficients applied to standardized feature values.
# The signs match the published model: every feature is positively
# associated with HR-deficiency. Magnitudes are demonstration-grade
# approximations of the Davies 2017 supplementary values; they should
# be re-validated against the original supplementary table before any
# clinical or research use.
HRDETECT_COEFFICIENTS: dict[str, float] = {
    "intercept": -3.364,
    "hrd_loh": 2.398,
    "e_del_mh_prop": 1.611,
    "sbs3": 0.910,
    "sbs8": 0.667,
    "rs3": 1.153,
    "rs5": 0.847,
}


# Feature standardization. The published model standardizes each feature
# (Box-Cox + z-score) before applying the coefficients. We approximate
# with simple z-scores using the means/SDs the demo would use; these
# numbers should be replaced with the validated training-set statistics
# for production use.
FEATURE_STATS: dict[str, tuple[float, float]] = {
    "hrd_loh": (12.0, 8.0),
    "e_del_mh_prop": (0.30, 0.18),
    "sbs3": (0.20, 0.18),
    "sbs8": (0.10, 0.10),
    "rs3": (0.18, 0.15),
    "rs5": (0.12, 0.12),
}


@dataclass
class SignatureFeatures:
    """The six HRDetect inputs. Units:

      hrd_loh        — count of HRD-LOH segments (>=15 Mb each)
      e_del_mh_prop  — fraction of small deletions with microhomology
      sbs3, sbs8     — proportion of SBS96 contribution from each sig
      rs3, rs5       — proportion of rearrangement signature contribution
    """
    hrd_loh: float
    e_del_mh_prop: float
    sbs3: float
    sbs8: float
    rs3: float
    rs5: float


@dataclass
class HRDetectResult:
    probability: float
    label: str  # "predicted_hr_deficient" | "predicted_hr_proficient" | "uncertain"
    features: SignatureFeatures
    feature_source: str  # "stub_extraction" | "user_provided"
    intercept: float
    coefficients: dict[str, float]
    duration_ms: int
    caveats: list[str]


def score(features: SignatureFeatures) -> float:
    """Logistic-regression evaluation. Standardizes each feature with the
    training-set mean/SD, multiplies by the coefficient, sums, and
    pushes through a sigmoid.
    """
    z_sum = HRDETECT_COEFFICIENTS["intercept"]
    for name in ("hrd_loh", "e_del_mh_prop", "sbs3", "sbs8", "rs3", "rs5"):
        mean, sd = FEATURE_STATS[name]
        x = getattr(features, name)
        z = (x - mean) / sd if sd > 0 else 0.0
        z_sum += HRDETECT_COEFFICIENTS[name] * z
    return 1.0 / (1.0 + math.exp(-z_sum))


def _label_for(prob: float) -> str:
    if prob >= 0.7:
        return "predicted_hr_deficient"
    if prob <= 0.2:
        return "predicted_hr_proficient"
    return "uncertain"


def extract_signatures_stub(vcf_path: Path) -> SignatureFeatures:
    """STUB. Real signature extraction needs whole-genome data and a
    multi-step deconvolution (SigProfiler / Signal / SigMA). Panel
    sequencing has nowhere near the mutation count required to fit
    a signature mixture, so we cannot compute SBS3/SBS8/RS3/RS5
    honestly from a typical clinical VCF.

    For demo purposes we generate a deterministic set of plausible
    signature counts from the VCF file's bytes so the same upload
    always produces the same score (lets the user re-run and see
    consistent output instead of flicker).

    Replace this with a real extraction pipeline (or a remote call to
    one) before treating any number out of this function as clinical.
    """
    # Hash the file bytes into a stable seed; map into plausible feature
    # ranges so the demo output is deterministic per-upload but not
    # trivially-zero.
    raw = vcf_path.read_bytes()
    h = abs(hash(raw))

    def in_range(rng: tuple[float, float]) -> float:
        lo, hi = rng
        # Simple hash-derived float in [lo, hi].
        return lo + ((h % 10_000) / 10_000.0) * (hi - lo)

    # Sample a different slice of the hash for each feature so they don't
    # all move together.
    h1, h2, h3, h4, h5, h6 = (
        abs(hash((raw, i))) for i in range(6)
    )

    def in_range_seeded(seed: int, rng: tuple[float, float]) -> float:
        lo, hi = rng
        return lo + ((seed % 10_000) / 10_000.0) * (hi - lo)

    return SignatureFeatures(
        hrd_loh=in_range_seeded(h1, (0, 30)),
        e_del_mh_prop=in_range_seeded(h2, (0.0, 0.7)),
        sbs3=in_range_seeded(h3, (0.0, 0.6)),
        sbs8=in_range_seeded(h4, (0.0, 0.4)),
        rs3=in_range_seeded(h5, (0.0, 0.5)),
        rs5=in_range_seeded(h6, (0.0, 0.3)),
    )


def run_from_vcf(vcf_path: Path) -> HRDetectResult:
    """End-to-end: extract signatures (STUB) then run the real model."""
    t0 = time.time()
    feats = extract_signatures_stub(vcf_path)
    prob = score(feats)
    return HRDetectResult(
        probability=prob,
        label=_label_for(prob),
        features=feats,
        feature_source="stub_extraction",
        intercept=HRDETECT_COEFFICIENTS["intercept"],
        coefficients={k: v for k, v in HRDETECT_COEFFICIENTS.items() if k != "intercept"},
        duration_ms=int((time.time() - t0) * 1000),
        caveats=[
            "Signature extraction is a documented stub. Real SBS3/SBS8/RS3/RS5 "
            "extraction needs whole-genome sequencing and a tool like "
            "SigProfiler; clinical panel VCFs lack the mutation count.",
            "HRDetect coefficients in this build are demo-grade approximations "
            "of the values reported in Davies 2017 supplementary table 6 — "
            "replace with the validated published values before any non-demo "
            "use.",
            "The model is for educational illustration. It does not constitute "
            "a clinical diagnosis or treatment recommendation.",
        ],
    )


def run_from_features(features: SignatureFeatures) -> HRDetectResult:
    """Score directly when the patient (or a clinician) already has the
    six WGS-derived numbers. Skips the stub extraction step entirely
    so the result reflects only the logistic-regression component.
    """
    t0 = time.time()
    prob = score(features)
    return HRDetectResult(
        probability=prob,
        label=_label_for(prob),
        features=features,
        feature_source="user_provided",
        intercept=HRDETECT_COEFFICIENTS["intercept"],
        coefficients={k: v for k, v in HRDETECT_COEFFICIENTS.items() if k != "intercept"},
        duration_ms=int((time.time() - t0) * 1000),
        caveats=[
            "HRDetect coefficients in this build are demo-grade approximations "
            "of the values reported in Davies 2017 supplementary table 6 — "
            "replace with the validated published values before any non-demo "
            "use.",
            "The model is for educational illustration. It does not constitute "
            "a clinical diagnosis or treatment recommendation.",
        ],
    )


def result_to_dict(r: HRDetectResult) -> dict[str, Any]:
    d = asdict(r)
    return d
