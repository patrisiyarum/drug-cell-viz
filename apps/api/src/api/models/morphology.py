from pydantic import BaseModel
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


class MorphologyMatch(BaseModel):
    rank: int
    similarity: float
    compound_name: str | None
    broad_sample_id: str
    image_url: str
    channel_urls: dict[str, str] | None = None
    cell_line: str
    perturbation_dose_um: float | None


class MorphologyResult(BaseModel):
    id: str
    smiles: str
    query_fingerprint: str
    matches: list[MorphologyMatch]
    control_url: str


class MorphologyResultRow(SQLModel, table=True):
    __tablename__ = "morphology_results"
    id: str = SQLField(primary_key=True)
    smiles: str
    matches_json: str
    control_url: str
