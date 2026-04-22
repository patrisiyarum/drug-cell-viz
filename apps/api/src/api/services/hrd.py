"""Homologous-recombination deficiency (HRD) composite score.

Aggregates every HR-related signal the app produces into a single call:
pathogenic-loss-of-function in any core HR gene (BRCA1, BRCA2, PALB2)
implies HR deficiency, which is the actionable clinical biomarker for
PARP-inhibitor therapy across breast, ovarian, pancreatic, and prostate
cancer.

Inputs the composite reads:
  1. Catalog variant matches from the patient's input (BRCA1_185delAG,
     BRCA2_6174delT, PALB2_1592delT, etc.) — pathogenic hits in the core
     HR panel are the strongest signal.
  2. The BRCA1 ML ensemble prediction (api.ml.infer.classify) — lets us
     call HR-deficient status even for BRCA1 variants not in the catalog.
  3. Moderate-penetrance hits (CHEK2, ATM) — downgraded to "elevated risk"
     rather than "HR-deficient," since these don't drive the same level of
     HR failure BRCA1/2 do.

Output labels:
  hr_deficient  — at least one core HR gene has a high-confidence loss
  hr_proficient — all core HR genes clear of known or predicted pathogenic
                  variants
  indeterminate — signal is ambiguous (e.g. a single high-confidence BRCA1
                  VUS with probability 0.45) or the patient gave us nothing
                  to evaluate

The score is an integer 0-100 where 100 = maximum HR-deficiency evidence.
Designed so a later UI can show a gauge, but the label is the clinically
meaningful output.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from api.ml.infer import classify as brca1_classify
from api.ml.infer import parse_hgvs_protein
from api.services.bc_catalog import VARIANTS

logger = logging.getLogger(__name__)

HrdLabel = Literal["hr_deficient", "hr_proficient", "indeterminate"]

# Core HR genes — loss of either copy has been shown to sensitize tumors to
# PARP inhibition. Keep this list tight; it's what determines the headline
# HR-deficient call.
CORE_HR_GENES: set[str] = {"BRCA1", "BRCA2", "PALB2"}

# Moderate-penetrance HR-adjacent genes. A pathogenic variant here elevates
# hereditary cancer risk and is clinically relevant, but by itself it does
# NOT make the tumor HR-deficient enough to reliably predict PARPi response.
MODERATE_HR_GENES: set[str] = {"CHEK2", "ATM", "BARD1", "RAD51C", "RAD51D", "BRIP1"}


@dataclass
class HrEvidence:
    """One piece of evidence contributing to the HRD composite."""

    gene: str
    variant_label: str
    source: Literal["catalog_pathogenic", "ml_prediction", "catalog_moderate"]
    weight: int                 # 0-60 points toward HR-deficient
    detail: str                 # human-readable sentence for the UI


@dataclass
class HrdScore:
    label: HrdLabel
    score: int                  # 0-100
    evidence: list[HrEvidence] = field(default_factory=list)
    # For the patient-facing UI.
    summary: str = ""
    parp_inhibitor_context: str = ""
    # Clinical caveats specific to HRD (not the general app-level ones).
    caveats: list[str] = field(default_factory=list)


def compute_hrd(
    resolved_variants: list[dict],
    classifiable_brca1_hgvs: list[str] | None = None,
) -> HrdScore:
    """Produce an HRD composite score from the patient's variant profile.

    Parameters
    ----------
    resolved_variants:
        Output of `api.services.analysis._resolve_variants` — list of dicts
        each with `gene_symbol`, `catalog_id`, `position`, `zygosity`,
        `label`.
    classifiable_brca1_hgvs:
        HGVS-protein strings for BRCA1 variants the ML classifier can score
        (from `AnalysisResult.classifiable_brca1_variants`). Passed in so the
        caller can reuse work already done in the analysis orchestrator.
    """
    evidence: list[HrEvidence] = []

    # --- 1) Catalog pathogenic variants in core HR genes ---
    for r in resolved_variants:
        cid = r.get("catalog_id")
        if not cid:
            continue
        var = VARIANTS.get(cid)
        if var is None:
            continue
        gene = var["gene_symbol"]
        sig = var["clinical_significance"]
        label_text = var["name"]

        if gene in CORE_HR_GENES and sig in ("pathogenic", "likely_pathogenic"):
            # Heterozygous pathogenic BRCA1/2/PALB2 is the classic germline
            # carrier state. The tumor almost always has a second hit, so we
            # call HR-deficient from a single heterozygous call.
            evidence.append(
                HrEvidence(
                    gene=gene,
                    variant_label=label_text,
                    source="catalog_pathogenic",
                    weight=60,
                    detail=(
                        f"Germline {gene} pathogenic variant "
                        f"({label_text}). Tumors arising on this background "
                        "usually lose the second BRCA allele, leading to HR "
                        "deficiency."
                    ),
                )
            )
        elif gene in MODERATE_HR_GENES and sig in ("pathogenic", "likely_pathogenic"):
            evidence.append(
                HrEvidence(
                    gene=gene,
                    variant_label=label_text,
                    source="catalog_moderate",
                    weight=15,
                    detail=(
                        f"Germline {gene} pathogenic variant "
                        f"({label_text}). Moderate-penetrance HR-adjacent "
                        "gene. Elevates hereditary cancer risk but does "
                        "not by itself imply PARPi-sensitive HR deficiency."
                    ),
                )
            )

    # --- 2) BRCA1 ML classifier predictions for non-catalog variants ---
    if classifiable_brca1_hgvs:
        for hgvs in classifiable_brca1_hgvs:
            try:
                ref, pos, alt = parse_hgvs_protein(hgvs)
            except Exception:
                continue
            try:
                pred = brca1_classify(ref, pos, alt)
            except Exception as exc:
                logger.info("BRCA1 classifier skipped %s: %s", hgvs, exc)
                continue
            # Only count high-confidence LOF calls toward HRD. Uncertain
            # predictions shouldn't drive the headline clinical call.
            p = pred.get("probability_loss_of_function", 0.0)
            conformal_label = (pred.get("conformal") or {}).get("label")
            if conformal_label == "loss_of_function" and p >= 0.70:
                evidence.append(
                    HrEvidence(
                        gene="BRCA1",
                        variant_label=hgvs,
                        source="ml_prediction",
                        weight=40,
                        detail=(
                            f"ML ensemble predicts BRCA1 {hgvs} is "
                            f"loss-of-function at {p*100:.0f}% probability "
                            "with high confidence (80%-coverage conformal "
                            "set is a singleton). This is a model call, not "
                            "an expert classification; confirm via ENIGMA "
                            "or clinical lab."
                        ),
                    )
                )

    # --- 3) Aggregate into a score + label ---
    score = min(100, sum(e.weight for e in evidence))
    core_hits = any(e.gene in CORE_HR_GENES and e.weight >= 40 for e in evidence)
    moderate_hits = any(e.gene in MODERATE_HR_GENES for e in evidence)

    if core_hits:
        label: HrdLabel = "hr_deficient"
        summary = (
            "HR-deficient profile. At least one core homologous-recombination "
            "gene (BRCA1, BRCA2, or PALB2) carries a pathogenic or "
            "predicted loss-of-function variant. This is the clinically "
            "actionable signal for PARP-inhibitor therapy."
        )
        parp_ctx = (
            "PARP inhibitors (olaparib, niraparib, rucaparib, talazoparib) "
            "are FDA-approved across breast, ovarian, pancreatic, and "
            "prostate cancer for patients with this biomarker profile. Your "
            "oncologist decides which drug and setting fits the tumor type."
        )
    elif moderate_hits and score >= 15:
        label = "indeterminate"
        summary = (
            "Moderate-penetrance HR-adjacent variant detected. This raises "
            "hereditary cancer risk and genetic-counseling relevance but "
            "does not by itself predict PARP-inhibitor response. Core BRCA1/"
            "BRCA2/PALB2 status is the stronger biomarker."
        )
        parp_ctx = (
            "PARP-inhibitor eligibility is not established by moderate-"
            "penetrance HR gene variants alone. Discuss tumor-level HRD "
            "testing (e.g. Myriad myChoice, FoundationOne CDx) with your "
            "oncologist."
        )
    elif not evidence:
        label = "indeterminate"
        summary = (
            "No HR-gene variants entered or detected. The catalog covers "
            "germline BRCA1, BRCA2, and PALB2 founder/common variants; a "
            "fully comprehensive evaluation requires a clinical "
            "hereditary-cancer panel (Myriad, Ambry, Invitae) plus tumor "
            "HRD testing if indicated."
        )
        parp_ctx = (
            "Insufficient data to call PARP-inhibitor eligibility. "
            "Consider clinical germline panel + tumor HRD testing."
        )
    else:
        label = "indeterminate"
        summary = (
            "Mixed or sub-threshold signal. Variants were detected but none "
            "cleared the high-confidence bar for a definitive HR-deficient "
            "call."
        )
        parp_ctx = (
            "Discuss the specific variants with a clinical "
            "pharmacogenomicist and consider confirmatory testing."
        )

    caveats = [
        "This is a research-grade composite built from germline and ML "
        "signals only. It does NOT replace clinical-grade HRD testing "
        "(e.g. Myriad myChoice genomic-instability score, FoundationOne "
        "CDx) that looks at tumor-level signatures.",
        "PARP inhibitor eligibility always requires consultation with a "
        "qualified oncologist and confirmation on a CLIA-certified assay.",
    ]

    return HrdScore(
        label=label,
        score=score,
        evidence=evidence,
        summary=summary,
        parp_inhibitor_context=parp_ctx,
        caveats=caveats,
    )
