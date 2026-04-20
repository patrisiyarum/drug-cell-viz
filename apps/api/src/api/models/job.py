from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobKind(str, Enum):
    MOLECULAR = "molecular"
    MORPHOLOGY = "morphology"
    COMBINED = "combined"


class JobCreate(BaseModel):
    smiles: str = Field(..., description="Drug SMILES string", min_length=1, max_length=500)
    uniprot_id: str = Field(..., pattern=r"^[A-Z0-9]{6,10}$")
    kind: JobKind = JobKind.COMBINED


class JobRead(BaseModel):
    id: str
    kind: JobKind
    status: JobStatus
    smiles: str
    uniprot_id: str
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    molecular_result_id: str | None = None
    morphology_result_id: str | None = None


class Job(SQLModel, table=True):
    id: str = SQLField(primary_key=True)
    kind: JobKind
    status: JobStatus = JobStatus.PENDING
    smiles: str
    uniprot_id: str
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow)
    error: str | None = None
    molecular_result_id: str | None = None
    morphology_result_id: str | None = None
