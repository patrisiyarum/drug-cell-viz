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
    #
    # On hosts like Render the 176 MB checkpoint isn't shipped via git
    # (GitHub blocks files >100 MB). RADIOGENOMICS_MODEL_WEIGHTS_URL lets us
    # download it from a public URL (GitHub Release asset / S3 / HF Hub) on
    # first boot and cache it under local_storage_root for subsequent
    # restarts so we don't re-pull every container start.
    weights_path = await _resolve_radiogenomics_weights()
    if weights_path is not None:
        from api.services import radiogenomics as rg

        try:
            rg.set_model_weights(
                weights_path, backbone=settings.radiogenomics_backbone,
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "failed to wire radiogenomics model — staying on stub path",
            )

    yield
    await close_events()


async def _resolve_radiogenomics_weights():
    """Locate the radiogenomics checkpoint, downloading from a public URL
    if a local copy isn't present.

    Search order:
        1. settings.radiogenomics_model_weights (explicit path) — if the
           file exists, use it as-is.
        2. settings.radiogenomics_model_weights_url — download to
           local_storage_root / "models" / "fold0.pt" on first boot and
           cache for subsequent restarts.
        3. Otherwise, return None and the API stays on the stub path.

    Returns a Path to a usable checkpoint, or None if neither produced one.
    Never raises — failures fall through to None so the API stays serving.
    """
    from pathlib import Path

    if settings.radiogenomics_model_weights:
        explicit = Path(settings.radiogenomics_model_weights)
        if explicit.exists():
            return explicit
        logging.getLogger(__name__).warning(
            "RADIOGENOMICS_MODEL_WEIGHTS set to %s but file does not exist; "
            "falling back to URL download or stub", explicit,
        )

    url = settings.radiogenomics_model_weights_url.strip()
    if not url:
        return None

    cache_dir = settings.local_storage_root / "models"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "fold0.pt"

    if cache_path.exists():
        return cache_path

    log = logging.getLogger(__name__)
    log.info(
        "downloading radiogenomics checkpoint from %s → %s (one-time, ~176 MB)",
        url, cache_path,
    )
    try:
        import asyncio
        import urllib.request

        # Run the blocking download in a thread so we don't block the event loop.
        def _download() -> None:
            with urllib.request.urlopen(url, timeout=300) as resp:
                with cache_path.open("wb") as f:
                    while True:
                        chunk = resp.read(1 << 20)  # 1 MB chunks
                        if not chunk:
                            break
                        f.write(chunk)

        await asyncio.to_thread(_download)
        size_mb = cache_path.stat().st_size / 1_000_000
        log.info("radiogenomics checkpoint cached (%.1f MB)", size_mb)
        return cache_path
    except Exception:
        # Clean up partial download so the next restart can retry cleanly.
        if cache_path.exists():
            try:
                cache_path.unlink()
            except OSError:
                pass
        log.exception("failed to download radiogenomics checkpoint — staying on stub")
        return None


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

        # Seed three demo uploads for Maya — CT scan + VCF + scar report.
        # Each one checks its own filename existence so a partial seed (e.g.
        # if a previous boot crashed mid-upload-block) self-heals on the next
        # boot. Don't gate the entire block on "Maya has zero uploads" — that
        # left Render in a state where the patient + meds were seeded but
        # the upload block had silently failed and never retried.
        from datetime import datetime, timezone

        async def _ensure_upload(filename: str, **fields: object) -> None:
            existing = (await session.execute(
                select(PatientUpload).where(
                    PatientUpload.patient_id == "maya",
                    PatientUpload.filename == filename,
                )
            )).first()
            if existing is None:
                session.add(PatientUpload(
                    patient_id="maya", filename=filename, **fields,  # type: ignore[arg-type]
                ))

        # CT scan — TCGA-24-0975 (ground-truth HRD-positive TCGA-OV patient
        # the v1 CNN ensemble scores at p(HRD)=0.97). Replaced the original
        # TCGA-09-1659 fixture which was a non-HRD patient and thus
        # correctly predicted HR-proficient by the model.
        await _ensure_upload(
            filename="TCGA-24-0975_axial_ct.nii.gz",
            upload_kind="ct_scan",
            asset_url="/fixtures/maya_ct_scan.nii.gz",
            summary_json="HRD 97% (predicted hr deficient, high confidence)",
            uploaded_at=datetime(2025, 11, 5, 14, 22, tzinfo=timezone.utc),
        )
        await _ensure_upload(
            filename="maya_germline_brca_panel.vcf",
            upload_kind="vcf",
            asset_url=None,
            summary_json="1 variant detected: BRCA1 p.Cys61Gly (pathogenic)",
            uploaded_at=datetime(2025, 10, 28, 9, 41, tzinfo=timezone.utc),
        )
        # Maya's myChoice / FoundationOne CDx-style scar report — third
        # independent line of evidence (germline BRCA1 + radiogenomics CT +
        # scar score all converge on HR-deficient).
        await _ensure_upload(
            filename="maya_myChoice_HRD_scars.pdf",
            upload_kind="report",
            asset_url=None,
            summary_json="LOH 14 · LST 18 · NTAI 12 → HRD-sum 44 (HR-deficient, scar burden above Myriad cutoff of 42).",
            uploaded_at=datetime(2025, 11, 18, 11, 14, tzinfo=timezone.utc),
        )
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
