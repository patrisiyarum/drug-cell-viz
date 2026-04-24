"""Genome-scar-based HRD scoring.

Orthogonal to (and stronger than) the germline-variant-based HRD composite
in `services/hrd.py`. Germline pathogenic BRCA1/2 tells you the *carrier*
is at risk; genomic scars in the tumor tell you whether the tumor is
*currently* HR-deficient — which is the actual PARPi eligibility question.

This module implements the three-component scar scoring used by the FDA-
recognized clinical tests (Myriad myChoice, FoundationOne CDx HRD-sum) and
by the published HRDetect / CHORD frameworks:

    1. HRD-LOH  — Loss-of-Heterozygosity regions >= 15 Mb not covering
                  whole chromosomes. Counts how many such regions exist.
    2. LST      — Large-Scale State Transitions. Chromosome-arm breaks
                  >= 10 Mb where copy-number or allelic state changes.
    3. NTAI     — Telomeric Allelic Imbalance. Allele-imbalanced regions
                  extending to a telomere, not covering the whole chromosome.

    HRD-sum = LOH + LST + NTAI
    HRD+ when HRD-sum >= 42 (Myriad myChoice cutoff)

We do NOT re-implement structural-variant calling here. The scorer's input
is a pre-computed feature bundle that a caller produces either via:

  * a tumor BAM pass through `scarHRD` (R package, Sztupinszki 2018)
  * a pangenome-graph SV caller like `vg call`, `minigraph --call`, or
    `minigraph-cactus deconstruct` that emits per-region CN/BAF/LOH calls
  * Myriad's or Foundation's proprietary assay if the patient already has
    one and pastes the feature counts

This module owns the scoring logic; the wiring lives in `routes/hrd_scars.py`.
Keeping them separate means the Python package is usable from the CLI
(pipelines) as well as the API.

Reference:
  Sztupinszki Z et al., Detecting homologous recombination deficiency in
  breast cancer using the scarHRD R package. npj Breast Cancer, 2018.
  https://www.nature.com/articles/s41523-018-0066-6

  Davies H et al. (HRDetect). Nat Med 2017.
  https://www.nature.com/articles/nm.4292
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Clinical cutoff. Myriad myChoice uses 42; some literature uses 33 as
# "likely HR-deficient" borderline. We treat >= 42 as "HR-deficient" and
# 33-41 as "borderline — discuss tumor testing".
HRD_POSITIVE_CUTOFF = 42
HRD_BORDERLINE_CUTOFF = 33


HrdScarLabel = Literal["hr_deficient_scar", "borderline_scar", "hr_proficient_scar", "insufficient"]


@dataclass(frozen=True)
class HrdScarFeatures:
    """Three integer counts that feed the HRD-sum.

    Typical ranges in breast/ovarian:
        - HR-proficient tumors:  LOH ~ 5,  LST ~ 10,  NTAI ~ 8   → sum ~ 23
        - HR-deficient tumors:   LOH ~ 25, LST ~ 30,  NTAI ~ 15  → sum ~ 70
    """

    loh: int       # HRD-LOH: large LOH regions, count
    lst: int       # LST: large-scale state transitions, count
    ntai: int      # NTAI: telomeric allelic imbalance, count


@dataclass(frozen=True)
class HrdScarScore:
    """Full score output for the API / UI."""

    features: HrdScarFeatures
    hrd_sum: int
    label: HrdScarLabel
    summary: str
    interpretation: str
    caveats: list[str]


def score(features: HrdScarFeatures) -> HrdScarScore:
    """Compute HRD-sum and a patient-facing interpretation.

    The inputs are already-computed integer counts per category. Callers
    that have raw copy-number / allele-imbalance tracks should use one of
    the upstream tools (scarHRD, HRDetect, vg call + in-house aggregation)
    to reduce them to these three counts before calling this function.
    """
    for name, val in [("loh", features.loh), ("lst", features.lst), ("ntai", features.ntai)]:
        if val < 0:
            raise ValueError(f"{name} must be non-negative, got {val}")

    total = features.loh + features.lst + features.ntai

    if total >= HRD_POSITIVE_CUTOFF:
        label: HrdScarLabel = "hr_deficient_scar"
        summary = (
            f"The tumor shows {total} genomic scars total "
            f"({features.loh} LOH + {features.lst} LST + {features.ntai} NTAI), "
            f"above the Myriad myChoice positivity cutoff of {HRD_POSITIVE_CUTOFF}. "
            "This is the clinical signal that a tumor has lost HR repair and is "
            "sensitive to PARP inhibitors."
        )
        interpretation = (
            "Scar-positive tumors are eligible for PARP-inhibitor therapy under "
            "FDA biomarker rules regardless of germline BRCA status. This "
            "biomarker complements the germline analysis above."
        )
    elif total >= HRD_BORDERLINE_CUTOFF:
        label = "borderline_scar"
        summary = (
            f"Borderline scar burden ({total}): above the safety threshold "
            f"({HRD_BORDERLINE_CUTOFF}) but below the positivity cutoff "
            f"({HRD_POSITIVE_CUTOFF}). Ambiguous from this assay alone."
        )
        interpretation = (
            "Consider a second clinical HRD assay (FoundationOne CDx) or tumor "
            "functional testing (RAD51 foci immunofluorescence) before acting."
        )
    else:
        label = "hr_proficient_scar"
        summary = (
            f"Low scar burden ({total}). No genomic fingerprint of HR deficiency; "
            "the tumor looks HR-proficient at this level of resolution."
        )
        interpretation = (
            "PARP inhibitors are unlikely to be selectively effective in the "
            "absence of germline BRCA1/2 pathogenic variants and scar positivity."
        )

    caveats = [
        "Scar scoring requires a paired tumor/normal sample and aligned reads "
        "(BAM or CRAM). VCF-only pipelines cannot compute these counts; a "
        "caller like scarHRD, HRDetect, or vg-call feeding a pangenome graph "
        "is needed upstream.",
        "The Myriad cutoff (42) was established on breast and ovarian cohorts; "
        "pancreatic and prostate cancer may need recalibration.",
        "Scar scoring captures the historical HR state of the tumor. After "
        "PARPi exposure, revertant mutations can restore HR without changing "
        "the scar score, so scars predict first-line response better than "
        "later-line response.",
    ]

    return HrdScarScore(
        features=features,
        hrd_sum=total,
        label=label,
        summary=summary,
        interpretation=interpretation,
        caveats=caveats,
    )
