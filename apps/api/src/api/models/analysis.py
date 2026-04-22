"""Pydantic models for the variant-analysis flow (breast cancer PGx + pocket)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


class VariantInput(BaseModel):
    """A single variant the user wants analyzed.

    Two input modes:
      1. `catalog_id` — pick a pre-curated variant from VARIANTS
      2. `gene_symbol` + `protein_sequence` — paste your protein sequence for a
         supported gene; the server aligns to the wild-type and infers changes.
    """

    catalog_id: str | None = None
    gene_symbol: str | None = None
    protein_sequence: str | None = Field(None, max_length=6000)
    zygosity: Literal["heterozygous", "homozygous"] = "heterozygous"


class AnalysisCreate(BaseModel):
    drug_id: str = Field(..., description="Catalog drug id, e.g. 'tamoxifen'")
    variants: list[VariantInput] = Field(default_factory=list, max_length=20)


class PocketResidue(BaseModel):
    position: int
    wildtype_aa: str | None = None
    variant_aa: str | None = None
    min_distance_to_ligand_angstrom: float | None = None
    in_pocket: bool  # min_distance <= threshold (default 5 Å)


class PGxVerdict(BaseModel):
    """A single drug-gene-variant rule matching the user's input."""

    drug_name: str
    gene_symbol: str
    variant_label: str
    zygosity: str
    phenotype: str
    recommendation: str
    evidence_level: Literal["A", "B", "C", "D"]
    source: str


class GlossaryTerm(BaseModel):
    term: str
    definition: str


class HowWeKnow(BaseModel):
    source: str
    link: str
    summary: str


class PlainLanguage(BaseModel):
    """Patient-friendly translation of the clinical result."""

    what_you_see: str
    how_the_drug_works: str
    what_it_means_for_you: str
    next_steps: str
    questions_to_ask: list[str]
    how_we_know: HowWeKnow
    glossary: list[GlossaryTerm]


class HrdEvidence(BaseModel):
    """One evidence line feeding the HRD composite score."""

    gene: str
    variant_label: str
    source: Literal["catalog_pathogenic", "ml_prediction", "catalog_moderate"]
    weight: int
    detail: str


class HrdResult(BaseModel):
    """Homologous-recombination deficiency composite score.

    The single clinically actionable output for PARP-inhibitor eligibility
    in HR-deficient breast, ovarian, pancreatic, and prostate cancer.
    """

    label: Literal["hr_deficient", "hr_proficient", "indeterminate"]
    score: int                           # 0-100
    evidence: list[HrdEvidence]
    summary: str
    parp_inhibitor_context: str
    caveats: list[str]


class SuggestedDrug(BaseModel):
    """A drug that's actually relevant to the patient's pasted genes.

    Populated when the current drug's pathway doesn't involve any of the
    genes the patient provided, so the UI can offer a one-click switch.
    """

    id: str
    name: str
    reason: str  # why this drug is relevant, e.g. "targets BRCA1 via synthetic lethality"


class CurrentDrugAssessment(BaseModel):
    """Whether the drug the patient is already on is the right one for them.

    This is the "I'm on X, is that right?" use case — the patient knows what
    they're taking, supplies their variants, and gets an explicit
    confirmation or a pointer to a better-matched option without having to
    ask for a second oncology opinion.
    """

    verdict: Literal["well_matched", "acceptable", "review_needed", "unknown"]
    headline: str           # one-sentence summary for the UI card
    rationale: str          # why we gave this verdict, citing variants + rules
    # Separate from rationale so the UI can render the citation on its own
    # line (italic, small) instead of inline in the body paragraph.
    source: str | None = None
    better_options: list[SuggestedDrug] = []


class OffTargetStructure(BaseModel):
    """A protein structure for a gene the patient has a variant in, which is
    different from the drug's primary target.

    Used to render a second 3D viewer on the results page so patients can
    actually see their variant residue on its own protein — not just see
    "the drug bound to something unrelated."
    """

    gene_symbol: str
    gene_name: str
    uniprot_id: str
    protein_pdb_url: str
    # Residue positions carrying variants, 1-indexed. The frontend passes these
    # to Mol* as highlights.
    positions: list[int] = []
    # Short human-readable label for each position, e.g. "p.Cys61Gly" — used
    # as the card subtitle next to the gene.
    variant_labels: list[str] = []


class AnalysisResult(BaseModel):
    id: str
    drug_id: str
    drug_name: str
    target_gene: str
    target_uniprot: str
    # 3D visualization
    protein_pdb_url: str
    pose_pdb_url: str | None = None  # with ligand HETATM
    # Clinical layer
    pgx_verdicts: list[PGxVerdict]
    # Structural layer: variant residues and their pocket proximity
    pocket_residues: list[PocketResidue]
    # Overall summary the UI displays prominently
    headline: str
    headline_severity: Literal["info", "caution", "warning", "contraindicated", "benefit"]
    # Patient-friendly translation layer (no jargon)
    plain_language: PlainLanguage
    # Drug-vs-variants relevance check. When the patient's variants are not
    # in the drug's pathway, this warning is non-empty and `suggested_drugs`
    # lists drugs that *are* relevant to those variants.
    relevance_warning: str | None = None
    suggested_drugs: list[SuggestedDrug] = []
    # BRCA1 variants that can be fed to the Tier-3 HR-function classifier.
    # Protein-level HGVS strings like "p.C61G". Frameshift / splice variants
    # are excluded because the classifier only handles point AA changes.
    classifiable_brca1_variants: list[str] = []
    # When the patient's variants sit on genes OTHER than the drug's primary
    # target (e.g. olaparib + BRCA1 — olaparib binds PARP1, not BRCA1), we
    # still fetch those proteins' AlphaFold structures so the UI can show
    # the variant residue highlighted on its own protein. Without this
    # patients see only PARP1 + olaparib and nothing about BRCA1.
    off_target_structures: list["OffTargetStructure"] = []
    # Homologous-recombination deficiency composite. THE headline clinical
    # output for this app — PARP-inhibitor eligibility across breast,
    # ovarian, pancreatic, and prostate cancer.
    hrd: HrdResult | None = None
    # Second-opinion-style assessment of the currently-selected drug. Tells
    # a patient whether the drug they're already on is well-matched to their
    # genetics or whether there's a stronger option.
    current_drug_assessment: CurrentDrugAssessment | None = None
    disclaimers: list[str]
    created_at: datetime


class AnalysisRow(SQLModel, table=True):
    __tablename__ = "analysis_results"
    id: str = SQLField(primary_key=True)
    drug_id: str
    target_gene: str
    payload_json: str  # serialized AnalysisResult
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
