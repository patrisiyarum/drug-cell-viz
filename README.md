# drug-cell-viz

[![CI](https://github.com/patrisiyarum/drug-cell-viz/actions/workflows/ci.yml/badge.svg)](https://github.com/patrisiyarum/drug-cell-viz/actions/workflows/ci.yml)

A patient-facing **HR-deficiency (HRD) cancer interpreter**. Takes a patient's
genetic variants (catalog, protein-sequence paste, 23andMe file, or clinical
VCF) and returns everything they need to walk into an oncology appointment
prepared:

1. **Homologous-recombination deficiency composite score** — the headline
   clinical output. Aggregates BRCA1/BRCA2/PALB2 pathogenic calls, FDA-
   recognized moderate-penetrance genes (RAD51C/D, BRIP1, BARD1), Fanconi
   anemia family, and ML-predicted BRCA1 loss-of-function into a single
   HR-deficient / HR-proficient / indeterminate call. Drives PARP-inhibitor
   eligibility across breast, ovarian, pancreatic, and prostate cancer.
2. **"Is my current drug the right match?" assessment** — the second-opinion
   feature. For a patient already on a medication, gives an explicit verdict
   (well-matched / acceptable / review-needed / unknown) plus better-matched
   alternatives when they exist. Built for patients who can't always afford
   a second oncology opinion.
3. **3D molecular view** of the drug on its target protein (AlphaFold DB)
   with the patient's variant residues highlighted.
4. **BRCA1 / BRCA2 variant-effect prediction** from an XGBoost + AlphaMissense
   ensemble classifier trained on saturation genome editing data, with
   calibrated conformal prediction intervals and expert panel cross-reference
   (ENIGMA / BRCA Exchange).
5. **Downloadable doctor-visit PDF** — one click generates a full report
   (HRD result + current-drug assessment + PGx verdicts + questions to ask +
   sources) suitable for printing and bringing to an appointment.

Explicitly positioned as an **educational tool** that helps patients walk into
oncology appointments prepared. Never makes treatment recommendations of its
own, it always surfaces the evidence and cites the source.

### Where this sits in the HRD-research landscape

The HRD label is contested: the Friends of Cancer Research HRD Harmonization
Project (2024) ran 20 independent assays on matched samples and declined to
declare a gold standard, and ~30% of Myriad-HRD-positive patients fail PARP
inhibitors because scar scores are **historical** and don't reflect post-PARPi
reversion. This project is a working clinical-grade baseline for
patient-facing HRD interpretation; it's also a platform for the broader
research program mapped in [`docs/research-roadmap.md`](docs/research-roadmap.md)
— 11 concrete directions from panel-only HRD callers to pathology foundation-
model benchmarks to BRCA1/2 reversion predictors, each with a current baseline
(if we have one) and a concrete extension path. The HrdCard surfaces a
**Reversion Awareness** callout for patients on a PARP inhibitor to flag
exactly this static-vs-dynamic gap.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Next.js 15 (patient UI)                     │
│   Landing · /demo selector · /results/[id] · /build             │
│   Mol* 3D viewer · plain-English translator · 23andMe parser    │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTPS
┌───────────────────────────────▼─────────────────────────────────┐
│                      FastAPI (async Python)                     │
│                                                                 │
│  /api/bc/analyze  → drug × variants orchestrator                │
│  /api/brca1/*     → ensemble classifier (XGB + AlphaMissense)   │
│  /api/brca2/*     → BRCA2 DBD classifier (Huang 2025 SGE)       │
│  /blobs/*         → PDB + SVG static mount                      │
│                                                                 │
│  Services:                                                      │
│   · alphafold.py        AlphaFold DB fetch + disk cache         │
│   · docking.py          RDKit stub / Modal DiffDock adapter     │
│   · pocket.py           NumPy heavy-atom distance analysis      │
│   · variants.py         HGVS parse + auto-detect from sequence  │
│   · plain_language.py   jargon → patient-friendly translator    │
│   · brca_exchange.py    ENIGMA expert-panel lookup              │
└──┬──────────────────────┬──────────────────────┬───────────────┘
   │                      │                      │
   ▼                      ▼                      ▼
ARQ worker            Redis (KV)            Postgres
(docking, long ops)   (ARQ queue +          (analysis audit trail,
                       result cache)         job status)

 External:  AlphaFold DB · UniProt · BRCA Exchange · CPIC · FDA labels
 Training:  Findlay 2018 SGE · Huang 2025 SGE · AlphaMissense (DeepMind)
```

---

## Deploy to Render (one blueprint, zero surprises)

The repo ships a [`render.yaml`](./render.yaml) Blueprint. In the Render dashboard:

1. **New → Blueprint**, connect this GitHub repo, pick the `main` branch.
2. Render creates five services: API (Docker, with persistent disk), worker
   (Docker, shares the disk), web (Node/Next.js), Key-Value store, Postgres.
3. After the API service comes up with its auto-assigned URL (e.g.
   `https://drug-cell-viz-api.onrender.com`), open the **web** service's
   env vars and set `NEXT_PUBLIC_API_URL` to that exact URL. Trigger a
   redeploy of the web service. (`NEXT_PUBLIC_*` vars are baked at build
   time, so a manual set-then-redeploy is the simplest flow.)
4. Open the web service URL — you'll see the landing page, `/demo` selector,
   and `/build` flow live.

**Free-tier notes:**
- Postgres free tier expires after 90 days (Render's policy).
- Free-tier services spin down after 15 min of inactivity — first request
  after a cold start takes ~30s while the ML models warm up.
- Persistent disk is a paid add-on (~$0.25/GB/month). Drop it from
  `render.yaml` if you're happy to re-fetch AlphaFold structures on every
  restart (they're idempotent anyway).

**Hitting a paywall?** You can alternatively deploy just the API as a single
Docker service and run the frontend anywhere (Vercel, Cloudflare Pages).
The API is stateless except for Postgres + Redis + the blob disk.

---

## Variant report pipeline (Snakemake)

Same evidence + same ML classifier as the web app, exposed as a Snakemake
workflow you can point at a directory of VCFs.

```bash
uv sync --extra pipeline --package api
uv run --package api snakemake \
    --snakefile pipelines/Snakefile \
    --configfile pipelines/config.yaml \
    --cores 1
```

Ships with a synthetic test VCF that runs end-to-end in ~4 seconds. Four
rules: **normalize** → **filter_catalog** → **classify** → **render_text_report**.
Outputs per sample: `detections.tsv`, `classifications.tsv`, `report.json`,
`report.txt`. Full docs in [`pipelines/README.md`](./pipelines/README.md).

### Upstream: FASTQ → VCF on NVIDIA Clara Parabricks

`rules/fastq_to_vcf.smk` adds a GPU-accelerated upstream stage: paired-end
FASTQ in, aligned BAM + germline VCF out, via `pbrun fq2bam` and
`pbrun haplotypecaller` on an A100/H100. A CPU fallback (`bwa-mem2` +
GATK4) keeps the pipeline runnable without a GPU. A 30× WGS sample takes
~45 minutes on GPU vs ~9 hours on 32 CPU cores.

### Tumor signal: genome-graph HRD scars

`rules/genome_graph_sv.smk` realigns the tumor BAM onto an HPRC pangenome
graph with `vg giraffe` (or `minigraph --call`), emits a structural-variant
VCF, and aggregates the SVs into the three HRDetect / Myriad myChoice
scar features — **HRD-LOH + LST + NTAI**. The three counts feed a
Python scorer ([`api/services/hrd_scars.py`](apps/api/src/api/services/hrd_scars.py))
that returns the Myriad-style HRD-sum + three-tier label
(`hr_deficient_scar` ≥ 42, `borderline_scar` 33-41, `hr_proficient_scar`
below). The web UI surfaces the same scorer via `POST /api/hrd/scars`
and a compact card on the results page, so patients with a myChoice /
FoundationOne CDx report can type in the three counts and get the
interpretation without re-running the pipeline.

### Imaging path: CT upload → HRD prediction

`POST /api/radiogenomics/upload` accepts a DICOM zip or NIfTI file, runs
the crop → resample-to-96³ → HU-normalise preprocessing pipeline, and
returns an HRD probability. The preprocessing is shared with the
training pipeline in
[hrd-radiogenomics](https://github.com/patrisiyarum/hrd-radiogenomics),
a companion research repo doing CT → HRD transfer learning from Med3D /
MONAI pretrained 3D CNNs on TCGA-OV × TCIA paired data. Until that
project ships trained weights, the endpoint returns a labelled stub
prediction and the UI surfaces a "research prototype, model not yet
trained" card on `/build` Step 2.

---

## Quick start (local)

```bash
cp .env.example .env
docker compose up --build
#   api      → http://localhost:8000  (/healthz, /readyz)
#   worker   → processes jobs from Redis
#   redis    → localhost:6379
#   postgres → localhost:5432

cd apps/web
pnpm install
pnpm dev
# frontend   → http://localhost:3000
```

Open `http://localhost:3000/demo` and click through the Maya / Diana / Priya
patient cases. Or go to `/build` to upload your own 23andMe file or pick
from the curated variant catalog.

---

## Layered feature overview

| Layer | Default | Swap-in |
|---|---|---|
| AlphaFold protein structures | ✅ live AlphaFold DB + disk cache | n/a |
| Docking poses | ✅ RDKit stub (centroid placement) | 🔌 DiffDock on Modal A10G (`USE_MODAL_DOCKING=true`) |
| Pharmacogenomic rules | ✅ curated CPIC / FDA subset (10 drugs, 13 variants) | scripted ingest of full CPIC / PharmGKB |
| BRCA1 variant effect | ✅ XGBoost + AlphaMissense ensemble + conformal (AUROC 0.933) | retrain with ESM2 embeddings on Modal GPU |
| BRCA2 DBD variant effect | ✅ XGBoost baseline (AUROC 0.842) | retrain with BRCA2-aware domain features |
| Expert-panel classification | ✅ BRCA Exchange / ENIGMA lookup (graceful fallback) | n/a |
| 23andMe SNP parse | ✅ client-side (data never leaves the browser) | n/a |
| Clinical VCF upload | ✅ server-side cyvcf2, zygosity + PASS filter | VEP annotation pre-pass |
| Snakemake batch pipeline | ✅ 4 rules, ships with test VCF | bcftools norm + FASTA reference |
| 3D viewer | ✅ Mol* with variant highlighting + ligand auto-zoom | n/a |
| Rate limit, SSE, zip export | ✅ | n/a |

---

## Tests & CI

```bash
cd apps/api
uv sync --extra dev
uv run pytest -q
```

38 tests covering:
- BRCA1 / BRCA2 classifiers (known pathogenic/benign variants)
- Drug/gene relevance check (including the synthetic-lethality
  olaparib/BRCA1 case that's the subject of several regression tests)
- Plain-language translator (severity mapping, recommendation translation,
  drug-specific question generation, glossary triggers)
- Variant resolver (alignment, auto-detect gene from sequence)
- VCF ingestion (cyvcf2 parse → catalog match → zygosity → analysis)
- Snakemake pipeline end-to-end (runs the whole workflow against the
  fixture, asserts report.json contents)
- Morphology retrieval (Morgan fingerprints + SVG render)
- Docking stub (centroid placement + combined PDB emission)

GitHub Actions runs pytest + `tsc --noEmit` on every push to `main` and on
every PR. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## Data sources & attribution

| Source | What | License |
|---|---|---|
| [Findlay et al. 2018](https://pmc.ncbi.nlm.nih.gov/articles/PMC6181777/) | BRCA1 SGE functional scores (3,893 SNVs) | Nature supplementary data |
| [Huang et al. 2025](https://www.nature.com/articles/s41586-024-08388-8) | BRCA2 DBD SGE functional scores (4,404 missense) | Nature supplementary data |
| [AlphaMissense](https://www.science.org/doi/10.1126/science.adg7492) (DeepMind) | ~216M precomputed missense pathogenicity scores | CC BY-NC-SA 4.0 |
| [AlphaFold DB](https://alphafold.ebi.ac.uk/) | Per-gene protein structures | CC BY 4.0 |
| [UniProt](https://www.uniprot.org/) | Canonical protein sequences | CC BY 4.0 |
| [CPIC](https://cpicpgx.org/) / FDA labels | Pharmacogenomic guidance | Public guidelines |
| [BRCA Exchange](https://brcaexchange.org/) | ENIGMA expert classifications | Open data |

---

## Layout

```
apps/api/src/api/
  ├─ ml/                 BRCA1/2 classifiers (train.py, infer.py, infer_brca2.py)
  │   ├─ data/           Findlay 2018, Huang 2025, AlphaMissense BRCA1 slice
  │   └─ models/         trained XGBoost + ensemble + conformal metadata
  ├─ models/             Pydantic + SQLModel data contracts
  ├─ services/           alphafold, docking, pocket, variants, plain_language,
  │                      brca_exchange, storage, bc_catalog
  ├─ routes/             bc, brca1, brca2, jobs, molecular, morphology, export
  ├─ workers/            ARQ task definitions
  └─ main.py             FastAPI app + lifespan
apps/web/
  ├─ app/                Next.js App Router: /, /demo, /results/[id], /build
  ├─ components/         MolViewer, ResultsReport, Brca1FunctionCard, …
  └─ lib/                api client, types, twenty-three-and-me parser
infra/modal/             Modal GPU function for real DiffDock
render.yaml              One-click Render Blueprint
.github/workflows/       CI (pytest + tsc)
```

---

## Disclaimer

This is an educational tool. It is not a medical device, is not FDA-cleared,
and does not provide treatment recommendations. All evidence shown is
summarized from public sources (CPIC, FDA labels, ENIGMA / BRCA Exchange,
AlphaMissense). Every ML prediction is reported with held-out performance
metrics and known limitations. **Consult a qualified oncologist and a
clinical pharmacogenomicist** before making any treatment decision. Genetic
testing must be performed by a CLIA-certified laboratory.
