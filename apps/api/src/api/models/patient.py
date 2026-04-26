"""Patient profile + linked records (medications, symptoms, uploads).

Lightweight per-patient record-keeping, no auth — patients are keyed by
short stable IDs (e.g. "maya"). The intent is a kintsugi-style
patient-prep tool: keep a journal of what's been put into the body,
what symptoms are showing up, and what scans / labs have been uploaded,
so the patient walks into an oncology appointment with the receipts in
one place.

Tables:
    Patient            id, name, age, indication, drug_id, drug_name
    Medication         which drug, dose, when started/ended, notes
    Symptom            date, label, severity 1-10, notes
    PatientUpload      a CT scan / VCF / 23andMe file + the model output
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, SQLModel


# --- DB tables ---


class Patient(SQLModel, table=True):
    __tablename__ = "patient"

    id: str = Field(primary_key=True, max_length=64)
    name: str = Field(max_length=120)
    age: int
    indication: str = Field(max_length=240)
    # The drug they're currently on. Optional — a freshly-created patient may
    # not have one yet.
    drug_id: Optional[str] = Field(default=None, max_length=64)
    drug_name: Optional[str] = Field(default=None, max_length=120)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Medication(SQLModel, table=True):
    __tablename__ = "medication"

    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True, max_length=64)
    drug_name: str = Field(max_length=120)
    dose: Optional[str] = Field(default=None, max_length=80)
    started_at: Optional[date] = None
    ended_at: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Symptom(SQLModel, table=True):
    __tablename__ = "symptom"

    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True, max_length=64)
    occurred_on: date
    label: str = Field(max_length=120)
    severity: int = Field(ge=1, le=10)
    notes: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PatientUpload(SQLModel, table=True):
    __tablename__ = "patient_upload"

    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True, max_length=64)
    upload_kind: str = Field(max_length=24)  # "ct_scan" | "vcf" | "23andme" | "report"
    filename: str = Field(max_length=240)
    # Public URL of the resolved volume (CT) or the original file (VCF/23andme).
    # None when the file lives only as backend bytes, never published.
    asset_url: Optional[str] = Field(default=None, max_length=600)
    # JSON-serialised summary of what the upload produced (HRD probability,
    # variant count, etc). Free-form so each upload kind can store its own.
    summary_json: Optional[str] = Field(default=None, max_length=4000)
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


# --- API contracts (read/write) ---


class PatientRead(BaseModel):
    id: str
    name: str
    age: int
    indication: str
    drug_id: Optional[str]
    drug_name: Optional[str]


class PatientCreate(BaseModel):
    id: str = PydanticField(min_length=2, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = PydanticField(min_length=1, max_length=120)
    age: int = PydanticField(ge=0, le=130)
    indication: str = PydanticField(min_length=1, max_length=240)
    drug_id: Optional[str] = None
    drug_name: Optional[str] = None


class MedicationRead(BaseModel):
    id: int
    drug_name: str
    dose: Optional[str]
    started_at: Optional[date]
    ended_at: Optional[date]
    notes: Optional[str]


class MedicationCreate(BaseModel):
    drug_name: str = PydanticField(min_length=1, max_length=120)
    dose: Optional[str] = PydanticField(default=None, max_length=80)
    started_at: Optional[date] = None
    ended_at: Optional[date] = None
    notes: Optional[str] = PydanticField(default=None, max_length=500)


class SymptomRead(BaseModel):
    id: int
    occurred_on: date
    label: str
    severity: int
    notes: Optional[str]


class SymptomCreate(BaseModel):
    occurred_on: date
    label: str = PydanticField(min_length=1, max_length=120)
    severity: int = PydanticField(ge=1, le=10)
    notes: Optional[str] = PydanticField(default=None, max_length=500)


class PatientUploadRead(BaseModel):
    id: int
    upload_kind: str
    filename: str
    asset_url: Optional[str]
    summary_json: Optional[str]
    uploaded_at: datetime


class PatientUploadCreate(BaseModel):
    upload_kind: str = PydanticField(pattern=r"^(ct_scan|vcf|23andme|report)$")
    filename: str = PydanticField(min_length=1, max_length=240)
    asset_url: Optional[str] = PydanticField(default=None, max_length=600)
    summary_json: Optional[str] = PydanticField(default=None, max_length=4000)


class PatientFullProfile(BaseModel):
    """Bundled response for the profile page — patient + everything linked."""

    patient: PatientRead
    medications: list[MedicationRead]
    symptoms: list[SymptomRead]
    uploads: list[PatientUploadRead]
