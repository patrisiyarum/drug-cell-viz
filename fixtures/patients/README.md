# Example patient VCFs

Four hand-crafted patient VCFs that exercise the clinical pathways the app
handles. Coordinates are GRCh38, sites are drawn from `api.services.vcf._COORDS`,
and genotypes are chosen to demonstrate a specific clinical scenario per file.

These are **synthetic demonstrations**, not real patients. Use them to smoke-test
the `/build` clinical-VCF upload path without having to sequence an actual
person.

| File | Scenario | Drug to pick | Expected result |
|---|---|---|---|
| `patient_maya_brca1.vcf` | Heterozygous BRCA1 p.Cys61Gly carrier | olaparib or niraparib | HR-deficient. Well-matched. |
| `patient_diana_cyp2d6.vcf` | Homozygous CYP2D6*4 (poor metabolizer) | tamoxifen | Review needed. Consider alternatives. |
| `patient_capecitabine_risk.vcf` | Heterozygous DPYD*2A | capecitabine | Dose reduction recommended. |
| `patient_null.vcf` | No pathogenic HR / PGx variants | any | Indeterminate HRD. No red flags. |

Each file is a minimal spec-compliant VCF: one variant per file (two for the
homozygous Diana case), coordinate-normalised to GRCh38, all PASS filter.

## How to use

```bash
# via the web UI:
#   open http://localhost:3000/build → clinical VCF → Choose file →
#   pick the fixture → Choose drug → Run

# via the API directly:
curl -F "file=@fixtures/patients/patient_maya_brca1.vcf" \
    "http://localhost:8000/api/vcf/analyze?drug_id=olaparib" | jq .
```

## Honest caveats

- Real patient VCFs have hundreds to millions of records. These have one or
  two — just enough to trigger the catalog match we want to demonstrate.
- A real clinical VCF would carry depth / quality / allele-balance INFO
  fields. These omit them; the ingestor doesn't require them.
- Hand-crafted genotypes (0/1, 1/1) are obvious; a real VCF would reflect
  read counts.
- For a realistic population-sampled patient VCF, see
  `scripts/gnomad/synthesize_patient.py`.
