# gnomAD-based testing for drug-cell-viz

Scripts for pulling gnomAD data at the HR-panel gene regions and using it to
smoke-test the analysis pipeline. None of these require DACO approval —
gnomAD aggregate data is fully public, hosted on an S3 bucket with free
HTTPS access.

## What's here

| Script | What it does |
|---|---|
| `extract_hr_panel.sh` | Use tabix to stream BRCA1 / BRCA2 / PALB2 / ATM / CHEK2 / RAD51C / RAD51D / BRIP1 / BARD1 / PARP1 regions from gnomAD v4.1 into a small bgzipped VCF |
| `validate_catalog.py` | For every catalog variant in `bc_catalog.py`, check that the position + alleles match a real gnomAD record |
| `synthesize_patient.py` | Draw random genotypes at gnomAD frequencies to produce a realistic per-patient VCF, saved as `fixtures/synthetic_patient_<id>.vcf` |
| `brca1_vus_eval.py` | Run every gnomAD BRCA1 missense variant through `/api/brca1/classify`, compare the output against ENIGMA labels where available |

## Prereqs

```bash
brew install htslib       # tabix + bgzip
```

No Google Cloud auth required — gnomAD publishes its VCFs through an
anonymous S3 bucket (us-east-1) that tabix can read over HTTPS.

## Quick start

```bash
# 1. Pull the HR-panel slice (~30 MB) — takes 2-3 min on a reasonable connection
bash scripts/gnomad/extract_hr_panel.sh data/gnomad/hr_panel.vcf.gz

# 2. Validate that every catalog variant maps to a real gnomAD record
uv run python scripts/gnomad/validate_catalog.py \
    --gnomad data/gnomad/hr_panel.vcf.gz

# 3. Synthesise a fake patient and upload to /build
uv run python scripts/gnomad/synthesize_patient.py \
    --gnomad data/gnomad/hr_panel.vcf.gz \
    --out fixtures/synthetic_patient_042.vcf \
    --population nfe  # non-Finnish European; other options: afr, amr, eas, sas

# 4. Run the BRCA1 ML classifier against every gnomAD BRCA1 missense
uv run python scripts/gnomad/brca1_vus_eval.py \
    --gnomad data/gnomad/hr_panel.vcf.gz \
    --api http://localhost:8000 \
    --out reports/brca1_vus_eval.csv
```

## Gene coordinates used

Grch38 coordinates:

| Gene | Chrom | Start | End |
|---|---|---|---|
| BRCA1 | chr17 | 43,044,295 | 43,125,483 |
| BRCA2 | chr13 | 32,315,474 | 32,400,266 |
| PALB2 | chr16 | 23,603,160 | 23,641,310 |
| ATM | chr11 | 108,222,832 | 108,369,102 |
| CHEK2 | chr22 | 28,687,820 | 28,741,585 |
| RAD51C | chr17 | 58,692,573 | 58,735,461 |
| RAD51D | chr17 | 35,101,353 | 35,119,221 |
| BRIP1 | chr17 | 61,679,193 | 61,863,563 |
| BARD1 | chr2 | 214,725,646 | 214,808,175 |
| PARP1 | chr1 | 226,360,251 | 226,408,154 |

## Non-goals

- This does NOT turn gnomAD into individual patient data. gnomAD is
  aggregate allele frequencies; drug-cell-viz already has synthetic patient
  VCFs under `apps/api/tests/fixtures/` for end-to-end tests.
- This does NOT run the full ML evaluation at scale. Budget ~200 ms per
  BRCA1 variant through the classifier, so evaluating all ~2,000 gnomAD
  BRCA1 missense variants takes ~7 minutes of API time.
