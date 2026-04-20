# drug-cell-viz

Web app that takes a drug (SMILES) and a protein target (UniProt ID) and
returns two side-by-side visualizations:

- **Molecular view** — the ligand docked into the target's 3D structure
  (AlphaFold DB for the protein + RDKit stub docker or DiffDock on Modal for
  the pose)
- **Cell morphology view** — top nearest neighbors in a JUMP Cell
  Painting-style catalog, retrieved by Morgan-fingerprint similarity

Full spec: [CLAUDE.md](./CLAUDE.md).

---

## Quick start

```bash
cp .env.example .env
docker compose up --build
#   api      → http://localhost:8000
#   worker   → processes jobs from Redis
#   redis    → localhost:6379
#   postgres → localhost:5432

cd apps/web
pnpm install
pnpm dev
# frontend   → http://localhost:3000
```

Try it:
- **SMILES:** `CC1=C(C=C(C=C1)NC(=O)C2=CC=C(C=C2)CN3CCN(CC3)C)NC4=NC=CC(=N4)C5=CN=CC=C5` (imatinib)
- **UniProt:** `P00519` (ABL1)

You should see a 3D pose in Mol* on the left and an 8-tile cell grid on the
right. The status banner shows a download link for a zip of the job.

---

## What runs where

| Phase | Component | Default |
|---|---|---|
| 1 | AlphaFold DB fetch (httpx + local cache) | ✅ real |
| 1 | Docking (RDKit 3D conformer placed at protein centroid) | ✅ stub, default on |
| 2 | DiffDock on Modal (A10G GPU) | 🔌 opt-in via `USE_MODAL_DOCKING=true` |
| 3 | Morphology retrieval (Morgan fingerprint + Tanimoto) | ✅ real, against bundled 16-compound catalog |
| 3 | FAISS over real JUMP-CP embeddings | 🔌 run `scripts/download_jump_subset.py` + `build_faiss_index.py` |
| 4 | ARQ worker + Redis cache on `(smiles, uniprot_id)` | ✅ |
| 4 | SSE streaming at `/api/jobs/{id}/stream` | ✅ |
| 5 | Zip export at `/api/export/{id}.zip` | ✅ |
| 5 | Rate limiting (10 jobs/hour/IP by default) | ✅ |

The bundled catalog at `apps/api/src/api/services/catalog_data.py` has 16
well-known compounds with phenotype tags (kinase inhibitors, microtubule
disruptors, actin disruptors, DNA-damage agents, etc.). Thumbnails are
rendered server-side as SVG "cell mosaic" placeholders keyed to the
phenotype — so the UI works with zero external image downloads.

To swap in real JUMP-CP data, implement the two scripts in `scripts/` —
the retrieval path already speaks in `MorphologyMatch` records, so only the
index source needs to change.

---

## Enabling real DiffDock (Phase 2)

1. `pip install modal && modal token new` (once)
2. `cd infra/modal && modal deploy diffdock_fn.py`
3. In your `.env`: `USE_MODAL_DOCKING=true`
4. Restart the worker: `docker compose restart worker`

The worker will now call the deployed Modal function instead of the RDKit
stub. Expect ~45s per dock on A10G. The stub keeps working if Modal is
unreachable — flip the flag back.

---

## Layout

```
apps/api              FastAPI + SQLModel + ARQ worker
apps/web              Next.js 15 + Mol* + TanStack Query
infra/modal           DiffDock GPU function (deploy separately)
scripts/              one-time JUMP-CP download + FAISS index build
packages/shared-types OpenAPI-generated TS types (run scripts/generate_ts_types.sh)
```

---

## Tests

```bash
cd apps/api
uv sync --all-extras
uv run pytest
```

Two tests: morphology retrieval (RDKit fingerprints + SVG render) and the
docking stub (centroid placement + combined PDB emission). Neither needs
Redis, Postgres, or network — so they run in CI unchanged.

---

## Disclaimer

These predictions are computational hypotheses, not medical evidence.
Docking poses are approximations; morphology matches are retrieved from an
experimental dataset, not generated for your specific query. This tool is
for research exploration only and does not substitute for laboratory or
clinical validation.
