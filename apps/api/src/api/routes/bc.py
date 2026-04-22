"""Breast-cancer pharmacogenomic + variant-analysis routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from api.db import session_scope
from api.models import AnalysisCreate, AnalysisResult, AnalysisRow
from api.services import analysis as analysis_service
from api.services import pdf_report as pdf_report_service
from api.services.bc_catalog import DEMO_NOTE, DEMO_PATIENTS, DRUGS, GENES, VARIANTS

router = APIRouter(prefix="/api/bc", tags=["breast-cancer"])


# Plain-English gene role blurbs for the patient-facing picker. Tuned for
# "read aloud to a friend" — no acronyms unless defined, no jargon.
_PLAIN_GENE_ROLES: dict[str, str] = {
    "BRCA1": (
        "A DNA repair protein. Variants that break it make cells struggle to "
        "fix certain kinds of DNA damage, which is exactly what PARP-blocker "
        "drugs like olaparib exploit."
    ),
    "BRCA2": (
        "A DNA repair protein that works with BRCA1. Variants that break it "
        "also make cells sensitive to PARP-blocker drugs like olaparib."
    ),
    "ESR1": (
        "The estrogen receptor. Hormone-sensitive breast cancer cells grow "
        "when estrogen attaches to this protein. Some breast cancer drugs "
        "block it or degrade it."
    ),
    "ERBB2": (
        "Also called HER2. A cell-surface growth signal. When there's too "
        "much of it, or it's mutated, the cell keeps dividing. Trastuzumab "
        "and similar drugs target it."
    ),
    "PIK3CA": (
        "A growth-signaling enzyme inside the cell. When mutated in certain "
        "common spots, it's stuck 'on' and drives tumor growth. Alpelisib "
        "targets the mutated form specifically."
    ),
    "CYP2D6": (
        "A liver enzyme that activates or breaks down many medications, "
        "including tamoxifen. Your CYP2D6 genotype changes how much of the "
        "active drug your body makes."
    ),
    "DPYD": (
        "The enzyme that clears 5-FU (the active form of capecitabine) from "
        "your body. Low DPYD activity means the drug accumulates to "
        "dangerous levels at the standard dose."
    ),
    "CYP19A1": (
        "Makes estrogen from other hormones. The target of aromatase-blocker "
        "drugs like letrozole."
    ),
    "ABL1": (
        "An overactive growth-signal enzyme in chronic myeloid leukemia. "
        "The target of imatinib."
    ),
    "TYMS": (
        "An enzyme cancer cells need to build DNA. 5-FU (the active form of "
        "capecitabine) blocks it."
    ),
    "TPMT": (
        "Inactivates thiopurine drugs like mercaptopurine. Low TPMT activity "
        "means the drug accumulates and damages bone marrow."
    ),
    "UGT1A1": (
        "Clears SN-38 (the active form of irinotecan) from the body. Low "
        "UGT1A1 activity means severe side effects at standard doses."
    ),
    "PARP1": (
        "A DNA damage sensor. Olaparib blocks it. In tumors with broken BRCA1 "
        "or BRCA2, blocking PARP1 is selectively lethal to the cancer cells."
    ),
    "CDK4": (
        "A protein that tells cells to divide. Palbociclib and ribociclib "
        "block it (and its partner CDK6), pausing the cell cycle in "
        "hormone-receptor-positive breast cancer."
    ),
    "CDK6": (
        "Partner of CDK4; together they drive the cell cycle. Blocked by the "
        "same CDK4/6 inhibitors (palbociclib, ribociclib, abemaciclib)."
    ),
}


# Patient-facing one-liner per variant. What it DOES to you, not the molecular
# mechanism. Keep under ~180 chars.
_PLAIN_VARIANT_SUMMARIES: dict[str, str] = {
    "BRCA1_185delAG": (
        "An Ashkenazi-Jewish founder variant that breaks BRCA1. Carriers "
        "have higher lifetime risk of breast and ovarian cancer and are "
        "eligible for PARP-blocker drugs like olaparib."
    ),
    "BRCA1_C61G": (
        "A well-known pathogenic BRCA1 change in the RING region. Disrupts "
        "BRCA1 function and makes tumors sensitive to olaparib."
    ),
    "BRCA2_6174delT": (
        "Another Ashkenazi-Jewish founder variant, this time in BRCA2. Same "
        "implications as the BRCA1 founder variants."
    ),
    "ESR1_Y537S": (
        "An acquired mutation that makes the estrogen receptor stay 'on' "
        "even without estrogen. Often appears after aromatase-inhibitor "
        "treatment and reduces response to those drugs."
    ),
    "ESR1_D538G": (
        "Another 'stuck-on' estrogen receptor mutation. Usually shows up "
        "after long endocrine therapy and signals acquired resistance."
    ),
    "ERBB2_L755S": (
        "A HER2 kinase mutation that keeps the receptor active. Trastuzumab "
        "may still work; newer HER2 pills like tucatinib are more effective."
    ),
    "ERBB2_V777L": (
        "Another HER2-activating kinase mutation. Similar implications to L755S."
    ),
    "PIK3CA_H1047R": (
        "The most common PIK3CA hotspot mutation. Makes you eligible for "
        "alpelisib (an FDA-approved targeted therapy for PIK3CA-mutated "
        "HR+ breast cancer)."
    ),
    "PIK3CA_E545K": (
        "The second most common PIK3CA hotspot. Same implications as H1047R."
    ),
    "CYP2D6_star4": (
        "A variant that knocks out CYP2D6 activity. If you have two copies "
        "you're a 'poor metabolizer' and tamoxifen may not work well for you."
    ),
    "CYP2D6_star10": (
        "Reduces but doesn't eliminate CYP2D6 activity. Common in East Asian "
        "populations. Intermediate metabolizer status."
    ),
    "DPYD_star2A": (
        "Cuts DPD enzyme activity, which clears 5-FU from your body. One "
        "copy means 50% dose reduction for capecitabine; two copies means "
        "the drug should generally be avoided."
    ),
    "DPYD_c2846A_T": (
        "Another reduced-activity DPD variant. Heterozygotes typically need "
        "a 50% capecitabine dose reduction."
    ),
    "TPMT_star3A": (
        "The most common TPMT-deficiency variant. Homozygotes can't process "
        "mercaptopurine safely; heterozygotes need dose adjustment."
    ),
    "TPMT_star2": (
        "A rarer TPMT loss-of-function variant with the same clinical "
        "implications as *3A in heterozygotes."
    ),
    "UGT1A1_star28": (
        "The variant behind Gilbert's syndrome. Reduces your body's ability "
        "to clear the active form of irinotecan. Homozygotes need dose "
        "reduction to avoid severe side effects."
    ),
}


# Coarse grouping used by the patient-facing picker to organize variants
# by the kind of clinical question each gene answers.
_GENE_EFFECT_TYPES: dict[str, str] = {
    # Drug targets (the drug directly binds this protein)
    "ESR1": "drug_target",
    "ERBB2": "drug_target",
    "PIK3CA": "drug_target",
    "ABL1": "drug_target",
    "PARP1": "drug_target",
    "TYMS": "drug_target",
    "CYP19A1": "drug_target",
    "CDK4": "drug_target",
    "CDK6": "drug_target",
    # Drug metabolism (affects how your body processes the drug)
    "CYP2D6": "drug_metabolism",
    "DPYD": "drug_metabolism",
    "TPMT": "drug_metabolism",
    "UGT1A1": "drug_metabolism",
    # DNA repair / synthetic-lethality context
    "BRCA1": "dna_repair",
    "BRCA2": "dna_repair",
}


@router.get("/catalog")
async def get_catalog() -> dict:
    """Return drugs + genes + variants for the frontend pickers."""
    return {
        "drugs": [
            {
                "id": d["id"],
                "name": d["name"],
                "category": d["category"],
                "primary_target_gene": d["primary_target_gene"],
                "metabolizing_gene": d["metabolizing_gene"],
                "mechanism": d["mechanism"],
                "indication": d["breast_cancer_indication"],
                "supports_docking": bool(d["smiles"]),
            }
            for d in DRUGS.values()
        ],
        "genes": [
            {
                "symbol": g["symbol"],
                "name": g["name"],
                "uniprot_id": g["uniprot_id"],
                "role": g["role"],
                "plain_role": _PLAIN_GENE_ROLES.get(g["symbol"], g["role"]),
                "effect_type": _GENE_EFFECT_TYPES.get(g["symbol"], "other"),
            }
            for g in GENES.values()
        ],
        "variants": [
            {
                "id": v["id"],
                "gene_symbol": v["gene_symbol"],
                "name": v["name"],
                "hgvs_protein": v["hgvs_protein"],
                "residue_positions": v["residue_positions"],
                "clinical_significance": v["clinical_significance"],
                "effect_summary": v["effect_summary"],
                "plain_summary": _PLAIN_VARIANT_SUMMARIES.get(v["id"], v["effect_summary"]),
                "effect_type": _GENE_EFFECT_TYPES.get(v["gene_symbol"], "other"),
            }
            for v in VARIANTS.values()
        ],
    }


@router.post("/analyze", response_model=AnalysisResult, status_code=201)
async def analyze(payload: AnalysisCreate) -> AnalysisResult:
    try:
        result = await analysis_service.run_analysis(payload.drug_id, payload.variants)
    except analysis_service.AnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async with session_scope() as session:
        row = AnalysisRow(
            id=result.id,
            drug_id=result.drug_id,
            target_gene=result.target_gene,
            payload_json=result.model_dump_json(),
        )
        session.add(row)
        await session.commit()
    return result


@router.get("/analysis/{result_id}", response_model=AnalysisResult)
async def get_analysis(result_id: str) -> AnalysisResult:
    async with session_scope() as session:
        row = await session.get(AnalysisRow, result_id)
    if row is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return AnalysisResult(**json.loads(row.payload_json))


@router.get("/demos")
async def get_demos() -> dict:
    """Return preset demo patient profiles for the walkthrough."""
    return {"note": DEMO_NOTE, "patients": DEMO_PATIENTS}


class PdfReportRequest(BaseModel):
    # The client POSTs the full AnalysisResult back (we don't require the
    # backend to keep persistent state for this ephemeral PDF export). The
    # frontend already has the AnalysisResult in memory post-analysis.
    result: AnalysisResult
    patient_label: str | None = None


@router.post("/report.pdf")
async def download_pdf_report(payload: PdfReportRequest) -> Response:
    """Generate the doctor-visit PDF and stream it back as an attachment."""
    pdf = pdf_report_service.build_pdf(payload.result, payload.patient_label)
    filename = (
        f"pharmacogenomic-report-{payload.result.drug_id}"
        f"-{payload.result.id[:8]}.pdf"
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
