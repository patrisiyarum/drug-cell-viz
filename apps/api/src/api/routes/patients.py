"""Patient profile endpoints — full record, plus medication/symptom/upload CRUD.

Patients are keyed by short stable IDs (e.g. "maya"). No auth in this MVP;
the design intent is single-user-per-device, the way a paper notebook works.
A future iteration would gate this behind a real session.
"""

import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete as sa_delete
from sqlmodel import select

from api.db import session_scope
from api.models.patient import (
    Medication,
    MedicationCreate,
    MedicationRead,
    Patient,
    PatientCreate,
    PatientFullProfile,
    PatientRead,
    PatientUpload,
    PatientUploadCreate,
    PatientUploadRead,
    Symptom,
    SymptomCreate,
    SymptomRead,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patients", tags=["patients"])


def _patient_read(p: Patient) -> PatientRead:
    return PatientRead(
        id=p.id, name=p.name, age=p.age, indication=p.indication,
        drug_id=p.drug_id, drug_name=p.drug_name,
    )


def _med_read(m: Medication) -> MedicationRead:
    return MedicationRead(
        id=m.id or 0, drug_name=m.drug_name, dose=m.dose,
        started_at=m.started_at, ended_at=m.ended_at, notes=m.notes,
    )


def _sym_read(s: Symptom) -> SymptomRead:
    return SymptomRead(
        id=s.id or 0, occurred_on=s.occurred_on, label=s.label,
        severity=s.severity, notes=s.notes,
    )


def _upload_read(u: PatientUpload) -> PatientUploadRead:
    return PatientUploadRead(
        id=u.id or 0, upload_kind=u.upload_kind, filename=u.filename,
        asset_url=u.asset_url, summary_json=u.summary_json,
        uploaded_at=u.uploaded_at,
    )


# ---------------------------------------------------------------------------
# Profile root
# ---------------------------------------------------------------------------

@router.get("/{patient_id}", response_model=PatientFullProfile)
async def get_patient_profile(patient_id: str) -> PatientFullProfile:
    async with session_scope() as session:
        p = await session.get(Patient, patient_id)
        if p is None:
            raise HTTPException(status_code=404, detail=f"patient {patient_id!r} not found")
        meds = (
            await session.execute(
                select(Medication).where(Medication.patient_id == patient_id)
                .order_by(Medication.started_at.desc().nullslast(), Medication.id.desc()),
            )
        ).scalars().all()
        symptoms = (
            await session.execute(
                select(Symptom).where(Symptom.patient_id == patient_id)
                .order_by(Symptom.occurred_on.desc(), Symptom.id.desc()),
            )
        ).scalars().all()
        uploads = (
            await session.execute(
                select(PatientUpload).where(PatientUpload.patient_id == patient_id)
                .order_by(PatientUpload.uploaded_at.desc()),
            )
        ).scalars().all()

    return PatientFullProfile(
        patient=_patient_read(p),
        medications=[_med_read(m) for m in meds],
        symptoms=[_sym_read(s) for s in symptoms],
        uploads=[_upload_read(u) for u in uploads],
    )


@router.post("", response_model=PatientRead, status_code=201)
async def create_patient(body: PatientCreate) -> PatientRead:
    async with session_scope() as session:
        existing = await session.get(Patient, body.id)
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"patient {body.id!r} already exists")
        p = Patient(**body.model_dump())
        session.add(p)
        await session.commit()
        await session.refresh(p)
    return _patient_read(p)


# ---------------------------------------------------------------------------
# Medications
# ---------------------------------------------------------------------------

@router.post("/{patient_id}/medications", response_model=MedicationRead, status_code=201)
async def add_medication(
    patient_id: str, body: MedicationCreate,
) -> MedicationRead:
    async with session_scope() as session:
        if (await session.get(Patient, patient_id)) is None:
            raise HTTPException(status_code=404, detail=f"patient {patient_id!r} not found")
        m = Medication(patient_id=patient_id, **body.model_dump())
        session.add(m)
        await session.commit()
        await session.refresh(m)
    return _med_read(m)


@router.delete("/{patient_id}/medications/{medication_id}", status_code=204)
async def delete_medication(patient_id: str, medication_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            sa_delete(Medication).where(
                Medication.id == medication_id,
                Medication.patient_id == patient_id,
            ),
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Symptoms
# ---------------------------------------------------------------------------

@router.post("/{patient_id}/symptoms", response_model=SymptomRead, status_code=201)
async def add_symptom(patient_id: str, body: SymptomCreate) -> SymptomRead:
    async with session_scope() as session:
        if (await session.get(Patient, patient_id)) is None:
            raise HTTPException(status_code=404, detail=f"patient {patient_id!r} not found")
        s = Symptom(patient_id=patient_id, **body.model_dump())
        session.add(s)
        await session.commit()
        await session.refresh(s)
    return _sym_read(s)


@router.delete("/{patient_id}/symptoms/{symptom_id}", status_code=204)
async def delete_symptom(patient_id: str, symptom_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            sa_delete(Symptom).where(
                Symptom.id == symptom_id,
                Symptom.patient_id == patient_id,
            ),
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

@router.post("/{patient_id}/uploads", response_model=PatientUploadRead, status_code=201)
async def add_upload(patient_id: str, body: PatientUploadCreate) -> PatientUploadRead:
    async with session_scope() as session:
        if (await session.get(Patient, patient_id)) is None:
            raise HTTPException(status_code=404, detail=f"patient {patient_id!r} not found")
        u = PatientUpload(patient_id=patient_id, **body.model_dump())
        session.add(u)
        await session.commit()
        await session.refresh(u)
    return _upload_read(u)


@router.delete("/{patient_id}/uploads/{upload_id}", status_code=204)
async def delete_upload(patient_id: str, upload_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            sa_delete(PatientUpload).where(
                PatientUpload.id == upload_id,
                PatientUpload.patient_id == patient_id,
            ),
        )
        await session.commit()
