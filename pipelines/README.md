# Variant report pipeline (Snakemake)

A four-step workflow that takes a VCF and emits per-sample pharmacogenomic
reports. Same evidence base as the web app, same ML classifier, just via a
batch pipeline that you can point at a whole directory of samples.

```
VCF  →  normalize  →  filter_catalog  →  classify  →  render_text_report
```

## Quick start

```bash
# One-time: install pipeline extras
cd apps/api
uv sync --extra pipeline

# From the repo root, run against the bundled fixture
cd ..
uv run --package api snakemake \
    --snakefile pipelines/Snakefile \
    --configfile pipelines/config.yaml \
    --cores 1
```

You should see `5 of 5 steps (100%) done` within a few seconds and the output
in `results/test_sample/`.

## Outputs

Per sample, under `results/<sample>/`:

| File | What it is |
|---|---|
| `normalized.vcf` | After the normalize step (split multi-allelic, drop ref-only) |
| `filtered.vcf` | PASS records inside our catalog loci (± 1kb) |
| `detections.tsv` | One row per catalog match: sample, catalog_id, gene, chrom/pos, zygosity |
| `classifications.tsv` | BRCA1 variants with ML-predicted loss-of-function probability |
| `report.json` | Full structured report: detections + PGx verdicts + plain-language + ML |
| `report.txt` | Human-readable summary that a clinician can read directly |
| `logs/*.log` | Per-rule log files |

## Add your own samples

Edit `pipelines/config.yaml`:

```yaml
samples:
  NA12878:
    vcf: /path/to/NA12878.vcf.gz
    drug_id: olaparib      # optional, per-sample override
  my_patient:
    vcf: /data/my_patient.vcf
    drug_id: tamoxifen
```

Snakemake will automatically run all four rules on every sample in parallel
if you pass `--cores N`.

## Rules

### `normalize`

Splits multi-allelic records so each line has exactly one ALT, drops records
with empty ALT. For production VCFs with complex indels, replace the Python
body with `bcftools norm -m-any -f REF.fa` — the interface is identical.

### `filter_catalog`

Keeps PASS records within 1 kb of any of our catalog coordinates (CYP2D6*4,
DPYD*2A, DPYD c.2846A>T, TPMT*3A markers, TPMT*2, BRCA1 p.Cys61Gly). The
flanking window is there to catch linked SNVs like the two markers that
jointly define TPMT*3A.

### `classify`

- Matches records to catalog variants using our shared
  `api.services.vcf.ingest` function (same path the live API uses).
- Collapses detections into `VariantInput` records and runs
  `api.services.analysis.run_analysis` against the sample's drug choice.
- For any BRCA1 missense variant found, runs the ensemble classifier
  (XGBoost + AlphaMissense + split-conformal) via `api.ml.infer.classify`.
- Emits `detections.tsv`, `classifications.tsv`, and `report.json`.

### `render_text_report`

Renders a plain-text summary of `report.json` suitable for reading in a
terminal or forwarding in an email.

## Swap-ins for real clinical use

- **Reference FASTA + bcftools** in `normalize`: one-line subprocess call.
- **VEP annotation** before `filter_catalog`: adds HGVS-protein so the BRCA1
  classifier sees every missense, not just those in our curated catalog.
- **gnomAD AF filter**: drop variants with AF > 1% before classification.
- **Parallel per-sample execution**: already supported — pass `--cores N`.

## Upstream: FASTQ → VCF via NVIDIA Clara Parabricks

`rules/fastq_to_vcf.smk` adds an optional upstream stage that accepts
paired-end FASTQ and produces a BAM + VCF using NVIDIA Clara Parabricks
on a CUDA-capable GPU. Configure samples under `fastq_samples:` and
select the backend with `fastq_backend: parabricks`.

Runtime comparison on a 30× whole-genome sample:

| Backend | Environment | Wall time |
|---|---|---|
| `parabricks` (default) | A100 / H100 via docker or singularity + NGC image | ~45 min |
| `bwa_gatk` (fallback) | 32 CPU cores, BWA-MEM 2 + GATK4 HaplotypeCaller | ~9 h |

Both emit the same bgzipped VCF so downstream `normalize` / `filter_catalog`
/ `classify` don't need to change. Parabricks docs:
<https://docs.nvidia.com/clara/parabricks/latest/gettingstarted.html>.

Set up once:

```yaml
# pipelines/config.yaml
reference_fa: /data/genome/GRCh38.fa
parabricks_image: nvcr.io/nvidia/clara/clara-parabricks:4.3.1-1
fastq_backend: parabricks

fastq_samples:
  patient_42:
    fastq_r1: data/raw/patient_42_R1.fastq.gz
    fastq_r2: data/raw/patient_42_R2.fastq.gz
```

## Tumor signal: genome-graph SV calls + HRDetect scar score

`rules/genome_graph_sv.smk` re-aligns the tumor BAM onto a pangenome
(HPRC gbz graph) with `vg giraffe` (or `minigraph --call`), emits a
structural-variant VCF, then aggregates the SVs into the three
HRDetect / Myriad myChoice scar features — HRD-LOH, LST, NTAI.

The scoring logic lives in `apps/api/src/api/services/hrd_scars.py` and
is the same code path the API endpoint `POST /api/hrd/scars` uses, so
the pipeline and the web app share one implementation:

```
aligned.bam
    │
    ▼
vg giraffe / minigraph --call      ← pangenome-graph realignment
    │
    ▼
scars.vcf.gz                       ← SV calls (bubbles + genotypes)
    │
    ▼
extract_hrd_features.py            ← count LOH + LST + NTAI
    │
    ▼
hrd_features.json                  ← three integers
    │
    ▼
score_hrd_scars.py                 ← api.services.hrd_scars.score()
    │
    ▼
hrd_scars.json                     ← label + sum + interpretation
```

HRD-sum ≥ 42 → `hr_deficient_scar` (Myriad myChoice cutoff). Sums between
33 and 41 are flagged as borderline; below 33 the tumor is scored
`hr_proficient_scar`.

Config:

```yaml
pangenome_graph: /data/graphs/hprc-v1.1.gbz
graph_backend: vg              # or "minigraph"
```

## Non-goals

- Clinical-grade FDA-cleared HRD assay: use Myriad myChoice, FoundationOne
  CDx, or a CLIA-certified lab. Our scar scorer is a demonstration of the
  method, not a certified device.
