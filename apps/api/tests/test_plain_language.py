"""Tests for the plain-language translator."""

from __future__ import annotations

from api.models import PGxVerdict, PocketResidue
from api.services import plain_language as pl


def _make_verdict(
    phenotype: str = "poor metabolizer",
    recommendation: str = "CPIC recommends an alternative hormonal therapy.",
    evidence_level: str = "A",
    gene: str = "CYP2D6",
    variant_label: str = "CYP2D6*4",
    source: str = "CPIC 2018 tamoxifen/CYP2D6 guideline",
    zygosity: str = "homozygous",
) -> PGxVerdict:
    return PGxVerdict(
        drug_name="Tamoxifen",
        gene_symbol=gene,
        variant_label=variant_label,
        zygosity=zygosity,
        phenotype=phenotype,
        recommendation=recommendation,
        evidence_level=evidence_level,  # type: ignore[arg-type]
        source=source,
    )


def test_caution_severity_adds_doctor_mention() -> None:
    out = pl.build_plain_language(
        drug_id="tamoxifen",
        target_gene="ESR1",
        target_uniprot="P03372",
        pgx_verdicts=[_make_verdict()],
        pocket_residues=[],
        headline_severity="caution",
        has_pose=True,
    )
    assert "doctor" in out.what_it_means_for_you.lower()
    assert "tamoxifen" in out.what_it_means_for_you.lower()


def test_fda_benefit_phrased_as_eligible() -> None:
    verdicts = [
        _make_verdict(
            phenotype="germline BRCA1 carrier",
            recommendation="FDA-approved indication. Olaparib is eligible for "
            "HER2-negative high-risk early or metastatic breast cancer.",
            source="FDA olaparib label",
            gene="BRCA1",
            variant_label="BRCA1 p.Cys61Gly",
            zygosity="heterozygous",
        )
    ]
    out = pl.build_plain_language(
        drug_id="olaparib",
        target_gene="PARP1",
        target_uniprot="P09874",
        pgx_verdicts=verdicts,
        pocket_residues=[],
        headline_severity="benefit",
        has_pose=True,
    )
    assert "eligible" in out.what_it_means_for_you.lower()


def test_capecitabine_avoid_is_patient_safe_wording() -> None:
    v = _make_verdict(
        phenotype="DPD deficiency",
        recommendation="CPIC: avoid fluoropyrimidines. Use an alternative regimen.",
        variant_label="DPYD*2A",
        gene="DPYD",
        source="CPIC 2017 fluoropyrimidines/DPYD guideline",
    )
    out = pl.build_plain_language(
        drug_id="capecitabine",
        target_gene="TYMS",
        target_uniprot="P04818",
        pgx_verdicts=[v],
        pocket_residues=[],
        headline_severity="contraindicated",
        has_pose=True,
    )
    low = out.what_it_means_for_you.lower()
    assert "avoid" in low or "should generally be avoided" in low
    assert "chemo" in low or "different" in low


def test_questions_are_drug_specific() -> None:
    out = pl.build_plain_language(
        drug_id="capecitabine",
        target_gene="TYMS",
        target_uniprot="P04818",
        pgx_verdicts=[_make_verdict(phenotype="intermediate DPD activity")],
        pocket_residues=[],
        headline_severity="caution",
        has_pose=True,
    )
    q = "\n".join(out.questions_to_ask).lower()
    assert "dose" in q


def test_glossary_grows_with_jargon_used() -> None:
    out_kinase = pl.build_plain_language(
        drug_id="imatinib",
        target_gene="ABL1",
        target_uniprot="P00519",
        pgx_verdicts=[],
        pocket_residues=[],
        headline_severity="benefit",
        has_pose=True,
    )
    assert "kinase" in {g.term for g in out_kinase.glossary}

    out_receptor = pl.build_plain_language(
        drug_id="tamoxifen",
        target_gene="ESR1",
        target_uniprot="P03372",
        pgx_verdicts=[],
        pocket_residues=[],
        headline_severity="benefit",
        has_pose=True,
    )
    assert "receptor" in {g.term for g in out_receptor.glossary}


def test_pocket_hit_adds_binding_pocket_glossary() -> None:
    pr = PocketResidue(
        position=61, wildtype_aa="C", variant_aa=None,
        min_distance_to_ligand_angstrom=2.5, in_pocket=True,
    )
    out = pl.build_plain_language(
        drug_id="tamoxifen",
        target_gene="ESR1",
        target_uniprot="P03372",
        pgx_verdicts=[],
        pocket_residues=[pr],
        headline_severity="warning",
        has_pose=True,
    )
    assert "binding pocket" in {g.term for g in out.glossary}
