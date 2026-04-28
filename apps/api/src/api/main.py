from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.config import settings
from api.db import check_db, init_db
from api.events import close as close_events
from api.routes import (
    bc_router,
    brca1_router,
    brca2_router,
    export_router,
    hrd_scars_router,
    jobs_limiter,
    jobs_router,
    molecular_router,
    morphology_router,
    patients_router,
    radiogenomics_router,
    screening_router,
    vcf_router,
)
from api.telemetry import configure_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=settings.log_level)
    settings.local_storage_root.mkdir(parents=True, exist_ok=True)
    configure_telemetry(app)
    await init_db()

    # Seed the demo patients (Maya, Diana, Priya) into the patient table on
    # first run so /patient/<id> works out of the box. Idempotent — re-runs
    # leave existing rows alone.
    try:
        await _seed_demo_patients()
    except Exception:
        logging.getLogger(__name__).exception("failed to seed demo patients")

    # Wire the radiogenomics model if a checkpoint was provisioned. If the
    # path is unset or missing, the upload endpoint stays on the stub path
    # and the UI surfaces the "model not trained" banner. Failing to load
    # does NOT crash the API — we log loudly and keep serving.
    if settings.radiogenomics_model_weights:
        from pathlib import Path

        from api.services import radiogenomics as rg

        weights_path = Path(settings.radiogenomics_model_weights)
        if weights_path.exists():
            try:
                rg.set_model_weights(
                    weights_path, backbone=settings.radiogenomics_backbone,
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "failed to wire radiogenomics model — staying on stub path",
                )
        else:
            logging.getLogger(__name__).warning(
                "RADIOGENOMICS_MODEL_WEIGHTS set to %s but file does not exist; "
                "serving stub predictions", weights_path,
            )

    yield
    await close_events()


app = FastAPI(title="drug-cell-viz API", version="0.1.0", lifespan=lifespan)

# CORS: the Next.js dev server runs on a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = jobs_limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(_req: Any, exc: RateLimitExceeded) -> Any:
    raise HTTPException(status_code=429, detail=f"rate limit exceeded: {exc.detail}")


app.include_router(jobs_router)
app.include_router(molecular_router)
app.include_router(morphology_router)
app.include_router(export_router)
app.include_router(bc_router)
app.include_router(brca1_router)
app.include_router(brca2_router)
app.include_router(vcf_router)
app.include_router(screening_router)
app.include_router(hrd_scars_router)
app.include_router(radiogenomics_router)
app.include_router(patients_router)

# Serve local blob storage so the frontend can fetch PDBs and thumbnails by URL.
if settings.storage_backend == "local":
    settings.local_storage_root.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/blobs",
        StaticFiles(directory=str(settings.local_storage_root)),
        name="blobs",
    )


async def _seed_demo_patients() -> None:
    """Insert Maya / Diana / Priya into the patient table if they're missing.

    Mirrors the in-catalog DEMO_PATIENTS so /patient/<id> renders correctly
    on the first visit without forcing the user to create profiles manually.
    Maya gets some seed medications + symptoms so her profile isn't empty.
    """
    from datetime import date

    from api.db import session_scope
    from api.models.patient import Medication, Patient, PatientUpload, Symptom

    seeds = [
        ("maya", "Maya", 41, "High-grade serous ovarian cancer, germline BRCA1+", "olaparib", "Olaparib (Lynparza)"),
        ("diana", "Diana", 52, "Recurrent ER+ ovarian cancer (germline panel clean for HR genes)", "tamoxifen", "Tamoxifen"),
        ("priya", "Priya", 58, "HER2-negative metastatic breast cancer, germline BRCA2+ (HRD-positive)", "olaparib", "Olaparib (Lynparza)"),
    ]
    async with session_scope() as session:
        for pid, name, age, indication, drug_id, drug_name in seeds:
            existing = await session.get(Patient, pid)
            if existing is not None:
                continue
            session.add(Patient(
                id=pid, name=name, age=age, indication=indication,
                drug_id=drug_id, drug_name=drug_name,
            ))
        await session.commit()

        # Sample medications + symptoms for Maya only — gives the demo
        # profile something concrete to render. Idempotent: only seeds if
        # she has zero existing medications.
        from sqlmodel import select
        existing_meds = (await session.execute(
            select(Medication).where(Medication.patient_id == "maya")
        )).first()
        if existing_meds is None:
            session.add(Medication(
                patient_id="maya", drug_name="Olaparib", dose="300 mg twice daily",
                started_at=date(2025, 11, 12), notes="Maintenance after platinum response.",
            ))
            session.add(Medication(
                patient_id="maya", drug_name="Carboplatin + Paclitaxel",
                dose="6 cycles, every 3 weeks",
                started_at=date(2025, 6, 4), ended_at=date(2025, 10, 22),
                notes="First-line chemotherapy. Completed.",
            ))
            session.add(Symptom(
                patient_id="maya", occurred_on=date(2025, 12, 18),
                label="Mild fatigue", severity=4,
                notes="Worse on day 5 of each cycle. Improves with rest.",
            ))
            session.add(Symptom(
                patient_id="maya", occurred_on=date(2025, 12, 22),
                label="Nausea", severity=3,
                notes="Manageable with anti-emetics.",
            ))
            await session.commit()

        # Seed two demo uploads for Maya — one CT scan, one VCF — pointing
        # at the static fixtures the web app already ships under /fixtures.
        # Idempotent: only seeds if she has zero existing uploads.
        from datetime import datetime, timezone
        existing_uploads = (await session.execute(
            select(PatientUpload).where(PatientUpload.patient_id == "maya")
        )).first()
        if existing_uploads is None:
            session.add(PatientUpload(
                patient_id="maya",
                upload_kind="ct_scan",
                # Swapped from TCGA-09-1659 (a non-HRD patient — CNN was
                # correctly predicting HR-proficient, breaking the demo) to
                # TCGA-24-0975, a ground-truth HRD-positive TCGA-OV patient
                # that the v1 5-fold CNN ensemble scores at p(HRD)=0.97 with
                # the API's preprocessing pipeline. Both germline + imaging
                # now point at HR-deficient.
                filename="TCGA-24-0975_axial_ct.nii.gz",
                asset_url="/fixtures/maya_ct_scan.nii.gz",
                summary_json="HRD 97% (predicted hr deficient, high confidence)",
                uploaded_at=datetime(2025, 11, 5, 14, 22, tzinfo=timezone.utc),
            ))
            session.add(PatientUpload(
                patient_id="maya",
                upload_kind="vcf",
                filename="maya_germline_brca_panel.vcf",
                asset_url=None,
                summary_json="1 variant detected: BRCA1 p.Cys61Gly (pathogenic)",
                uploaded_at=datetime(2025, 10, 28, 9, 41, tzinfo=timezone.utc),
            ))
            await session.commit()

        # Maya's myChoice / FoundationOne CDx-style scar report — a third
        # independent line of evidence (germline BRCA1 + radiogenomics CT +
        # scar score all agree). Seeded with its own existence check so it
        # backfills on existing DBs that already had Maya's CT + VCF.
        scar_existing = (await session.execute(
            select(PatientUpload).where(
                PatientUpload.patient_id == "maya",
                PatientUpload.filename == "maya_myChoice_HRD_scars.pdf",
            )
        )).first()
        if scar_existing is None:
            session.add(PatientUpload(
                patient_id="maya",
                upload_kind="report",
                filename="maya_myChoice_HRD_scars.pdf",
                asset_url=None,
                summary_json="LOH 14 · LST 18 · NTAI 12 → HRD-sum 44 (HR-deficient, scar burden above Myriad cutoff of 42).",
                uploaded_at=datetime(2025, 11, 18, 11, 14, tzinfo=timezone.utc),
            ))
            await session.commit()

        # ----- Seed Diana ---------------------------------------------------
        existing_diana_meds = (await session.execute(
            select(Medication).where(Medication.patient_id == "diana")
        )).first()
        if existing_diana_meds is None:
            session.add(Medication(
                patient_id="diana", drug_name="Tamoxifen", dose="20 mg daily",
                started_at=date(2025, 9, 18),
                notes="Hormonal therapy for ER+ disease. CYP2D6 *4/*4 reduces conversion to active form.",
            ))
            session.add(Medication(
                patient_id="diana", drug_name="Carboplatin",
                dose="AUC 5, every 3 weeks",
                started_at=date(2024, 11, 5), ended_at=date(2025, 4, 12),
                notes="Platinum chemotherapy. Completed; partial response.",
            ))
            session.add(Symptom(
                patient_id="diana", occurred_on=date(2025, 12, 14),
                label="Hot flashes", severity=6,
                notes="Frequent, especially evenings. Likely tamoxifen-related.",
            ))
            session.add(Symptom(
                patient_id="diana", occurred_on=date(2025, 12, 19),
                label="Joint stiffness", severity=4,
                notes="Mostly mornings. Loosens with activity.",
            ))
            session.add(Symptom(
                patient_id="diana", occurred_on=date(2025, 12, 23),
                label="Low energy", severity=5,
                notes="Persistent for ~2 weeks.",
            ))
            await session.commit()

        # ----- Seed Priya ---------------------------------------------------
        existing_priya_meds = (await session.execute(
            select(Medication).where(Medication.patient_id == "priya")
        )).first()
        if existing_priya_meds is None:
            session.add(Medication(
                patient_id="priya", drug_name="Olaparib", dose="300 mg twice daily",
                started_at=date(2025, 8, 22),
                notes="OlympiAD-indication. germline BRCA2 + scar-confirmed HRD.",
            ))
            session.add(Medication(
                patient_id="priya", drug_name="Capecitabine",
                dose="1000 mg/m² twice daily, days 1-14 / 21",
                started_at=date(2024, 9, 10), ended_at=date(2025, 6, 5),
                notes="Prior chemotherapy. Switched to olaparib after BRCA2 + HRD confirmation.",
            ))
            session.add(Symptom(
                patient_id="priya", occurred_on=date(2025, 12, 17),
                label="Anaemia (mild)", severity=4,
                notes="Known olaparib side effect. Hgb 11.2 last draw.",
            ))
            session.add(Symptom(
                patient_id="priya", occurred_on=date(2025, 12, 21),
                label="Fatigue", severity=5,
                notes="Improving since dose-tolerance period started.",
            ))
            await session.commit()

        existing_priya_uploads = (await session.execute(
            select(PatientUpload).where(PatientUpload.patient_id == "priya")
        )).first()
        if existing_priya_uploads is None:
            session.add(PatientUpload(
                patient_id="priya",
                upload_kind="vcf",
                filename="priya_germline_brca_panel.vcf",
                asset_url=None,
                summary_json="1 variant: BRCA2 c.5946delT (pathogenic). HRD pathway hit.",
                uploaded_at=datetime(2025, 7, 15, 10, 22, tzinfo=timezone.utc),
            ))
            # Tumor scar HRD report — Priya's headline HRD evidence since
            # breast cancer doesn't use CT-based radiogenomics. LOH 18 +
            # LST 22 + NTAI 16 = HRD-sum 56, well above the Myriad cutoff.
            session.add(PatientUpload(
                patient_id="priya",
                upload_kind="report",
                filename="priya_myChoice_HRD_scars.pdf",
                asset_url=None,
                summary_json="LOH 18 · LST 22 · NTAI 16 → HRD-sum 56 (HR-deficient, well above Myriad cutoff of 42).",
                uploaded_at=datetime(2025, 7, 28, 14, 5, tzinfo=timezone.utc),
            ))
            await session.commit()

        existing_diana_uploads = (await session.execute(
            select(PatientUpload).where(PatientUpload.patient_id == "diana")
        )).first()
        if existing_diana_uploads is None:
            session.add(PatientUpload(
                patient_id="diana",
                upload_kind="ct_scan",
                filename="TCGA-13-1411_abd_pel_ct.nii.gz",
                asset_url="/fixtures/diana_ct_scan.nii.gz",
                summary_json="HRD 76% (predicted hr deficient, high confidence) — somatic-HRD signal despite clean germline.",
                uploaded_at=datetime(2025, 11, 14, 10, 5, tzinfo=timezone.utc),
            ))
            session.add(PatientUpload(
                patient_id="diana",
                upload_kind="vcf",
                filename="diana_germline_panel.vcf",
                asset_url=None,
                summary_json="1 variant: CYP2D6 *4/*4 (poor metabolizer). HR-repair panel clean.",
                uploaded_at=datetime(2025, 10, 30, 14, 18, tzinfo=timezone.utc),
            ))
            session.add(PatientUpload(
                patient_id="diana",
                upload_kind="report",
                filename="myChoice_HRD_summary.pdf",
                asset_url=None,
                summary_json="Tumor scar test ordered after radiogenomics flag. Awaiting result.",
                uploaded_at=datetime(2025, 11, 20, 9, 30, tzinfo=timezone.utc),
            ))
            await session.commit()


_redis: redis.Redis = redis.from_url(settings.redis_url, decode_responses=True)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    try:
        checks["redis"] = bool(await _redis.ping())
    except Exception:
        checks["redis"] = False
    try:
        checks["db"] = await check_db()
    except Exception:
        checks["db"] = False

    if not all(checks.values()):
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ready", "checks": checks}
