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
    disclaimers: list[str]
    created_at: datetime


class AnalysisRow(SQLModel, table=True):
    __tablename__ = "analysis_results"
    id: str = SQLField(primary_key=True)
    drug_id: str
    target_gene: str
    payload_json: str  # serialized AnalysisResult
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
