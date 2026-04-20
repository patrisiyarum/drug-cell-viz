from typing import Literal

from pydantic import BaseModel
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


class DockingPose(BaseModel):
    rank: int
    confidence: float
    affinity_kcal_mol: float | None = None
    pdb_url: str


class MolecularResult(BaseModel):
    id: str
    uniprot_id: str
    smiles: str
    protein_pdb_url: str
    poses: list[DockingPose]
    source: Literal["alphafold_db", "alphafold2_colabfold", "pdb"]


class MolecularResultRow(SQLModel, table=True):
    __tablename__ = "molecular_results"
    id: str = SQLField(primary_key=True)
    uniprot_id: str
    smiles: str
    protein_pdb_url: str
    poses_json: str
    source: str
