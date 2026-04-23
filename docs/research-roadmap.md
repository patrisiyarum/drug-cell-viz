# HRD Research Roadmap

This project is a **working clinical-grade baseline** for patient-facing HR-deficiency
interpretation. It's also a platform for a broader research program on where AI can
make HRD measurement less fragile, more dynamic, and better-calibrated.

The "Where AI can break through in HRD cancer research" scan identified eleven
concrete directions worth pursuing. This document maps each one against what's
already shipped in this repo and what would need to be added. The intent is to
make the scope of the long-term program legible — so anyone reading the code can
see where the project sits on the path from "research-grade baseline" to "useful
to the field."

## The field's central tension

The HRD label is the gate to PARP-inhibitor eligibility, a ~$5B/year drug class
with years of OS benefit for responders. But the label itself is **historical,
single-modal, and contested**:

- The **Friends of Cancer Research HRD Harmonization Project (2024)** ran 20
  independent HRD assays on matched samples and declined to declare a gold
  standard. Only 2 of 4 commercial panels agreed with Myriad at >90% concordance.
- The Myriad myChoice **GIS ≥ 42 cutoff** is a quartile boundary from a 2016 TNBC
  study. Takaya 2020 argued for 63 in ovary; FoundationOne uses 16% or 21% LOH
  depending on indication.
- **~30% of Myriad-HRD-positive patients fail PARP inhibitors** (PRIMA, PAOLA-1)
  — the scar score records *past* HR state, not current.
- **~20% of post-PARPi ovarian tumors develop BRCA1/2 reversion mutations**
  (Silverman & Schonhoft 2025, Repare TRESR/ATTACC). Many are small in-frame indels
  missed by short-read panels.

This project's current HRD composite (`services/hrd.py` + the tumor-scar form in
`HrdCard`) lands firmly on the static-genomic-scar side of that tension. Every
research direction below pushes toward a more dynamic, multi-modal, or better-
calibrated label.

## What's already in this repo

| Capability | Implementation |
|---|---|
| Germline BRCA1/2 pathogenicity ensemble | `apps/api/src/api/ml/` — XGBoost on Findlay 2018 SGE + AlphaMissense + logistic meta-learner, split-conformal intervals at 80/90/95% coverage |
| BRCA2 DBD classifier | `ml/infer_brca2.py` — XGBoost on Huang 2025 SGE |
| HRD composite score | `services/hrd.py` — germline pathogenic + ML LOF + moderate-HR + FDA-PARPi-moderate |
| Myriad-style scar score | `services/hrd_scars.py` — HRD-LOH + LST + NTAI → HRD-sum + three-tier label |
| Clinical VCF ingestion | `services/vcf.py` — cyvcf2 parse + catalog match + zygosity |
| FASTQ → VCF | `pipelines/rules/fastq_to_vcf.smk` — NVIDIA Parabricks with BWA+GATK CPU fallback |
| Genome-graph SV calling | `pipelines/rules/genome_graph_sv.smk` — vg giraffe / minigraph → SV VCF → HRD scar features |
| BRCA Exchange / ENIGMA expert lookup | `services/brca_exchange.py` — falls back gracefully |
| Virtual screening | `services/screening.py` — pocket-fit + Morgan-fingerprint Tanimoto ranking |
| Patient-facing 3D view | Mol* with yellow variant overpaint + camera auto-focus |
| Evidence reporting | Plain-language translator + doctor-visit PDF |
| Infra | FastAPI async + Postgres + Redis + ARQ + SSE + RabbitMQ + OTel; Terraform for GCP + Render blueprint |

## Research directions

The numbering tracks the rank order from the source scan (ratio of impact to
tractability given public data and a single GPU).

### 1. BRCA1/2 reversion predictor

**Claim:** Fine-tuning ESM-2 or Nucleotide Transformer on MaveDB SGE data to
predict whether a candidate indel restores BRCA1/2 reading frame is one of the
most tractable single-GPU, 3-month projects in the field. Silverman & Schonhoft
(2025) found reversions in 44% of BRCA-associated tumors after prior PARPi.

**Baseline in repo:** none. The BRCA1 ensemble handles missense only.

**What to add:**
- `apps/api/src/api/ml/reversion.py` — ESM-2 backbone + indel-aware head
- Training data: MaveDB BRCA1 RING/BRCT + BRCA2 DBD SGE, subset to indel entries
- Ultra-low-VAF detector for ctDNA reversion screening (in-frame-restoring indels
  near known pathogenic sites — analogous to task-specific DeepVariant)
- UI: new "Reversion screen" subsection on the HRD card when a patient on a PARPi
  uploads follow-up ctDNA

**Interim ship:** `HrdCard` now shows a **Reversion Awareness** callout for patients
on PARPi to flag the ~20-30% reversion rate and suggest ctDNA monitoring cadence.

### 2. Pathology foundation model benchmark for HRD

**Claim:** No public benchmark exists for UNI2 / Virchow2 / H-Optimus /
CHIEF / CONCH / TITAN × ABMIL / CLAM / ACMIL on TCGA-OV + TCGA-BRCA HRD with
CPTAC external validation. HRDPath specifically found UNI underperformed
compared to H-Optimus — a concrete open puzzle.

**Baseline in repo:** none. No slide ingestion, no foundation-model hookup.

**What to add:**
- `apps/api/src/api/ml/slides/` — WSI preprocessing (libraries: `openslide-python`,
  `tiatoolbox`); foundation-model embedding pipeline; ABMIL / CLAM aggregators
- Snakemake rule `rules/wsi_hrd.smk` — embed slides in Modal GPU, aggregate,
  score HRD
- Dataset loaders for TCGA-OV (GDC), CPTAC-OV (PDC), PAOLA-1 (external)
- Published benchmark table as `docs/benchmarks/wsi_hrd.md`
- UI: "Upload H&E slide for HRD prediction" (feature-flagged; needs model weights
  + a lot of storage — likely a Modal GPU endpoint, not inline)

### 3. VUS-to-HRD bridging classifier

**Claim:** 85% of missense variants in the HR panel are ClinVar VUS.
AlphaMissense is accurate for BRCA1/2/PALB2/RAD51C but fails for ATM and CHEK2
(Ziogas 2024; Niu 2025). A classifier fusing AlphaMissense + ESM-1b/2 + EVE +
AlphaFold structural features + SGE functional scores with cross-gene transfer
learning would plug a major clinical gap.

**Baseline in repo:** partial. The BRCA1 ensemble uses XGBoost + AlphaMissense.
ESM, EVE, AlphaFold-structural features, and cross-gene transfer are all absent.

**What to add:**
- `apps/api/src/api/ml/features.py` — extend with ESM-2 per-variant embeddings
  (Hugging Face `facebook/esm2_t33_650M_UR50D` or similar), EVE scores (precomputed
  MSA-based), AlphaFold per-residue confidence (pLDDT + PAE)
- `apps/api/src/api/ml/bridging.py` — shared trunk + per-gene heads (BRCA1, BRCA2,
  PALB2, RAD51C, RAD51D, BRIP1, BARD1)
- Training: Findlay 2018 + Huang 2025 + Wiggins 2022 PALB2 SGE + any 2024-2025
  RAD51C/D saturation screens
- Evaluation: hold-out SGE test + external ClinVar expert-panel calls (as out-of-
  distribution reality check)
- UI: same opt-in prediction strip as current BRCA1, generalised across the HR panel

### 4. Panel-only HRD deep classifier

**Claim:** Most labs run ~500-gene panels, not WGS, so a panel-friendly HRD caller
that beats SigMA on ovarian panel data has enormous clinical pull.

**Baseline in repo:** none. Current HRD uses catalog variants + optional ML call
on a BRCA1 missense.

**What to add:**
- `apps/api/src/api/ml/panel_hrd.py` — downsample PCAWG to GENIE-style ~500-gene
  panels; train a transformer or graph neural network on the resulting sparse
  signal; evaluate against Myriad GIS on held-out test set
- Snakemake rule `rules/panel_hrd.smk` — input: panel VCF; output: HRD probability

### 5. Multi-modal HRD fusion model

**Claim:** CPTAC ovarian cohort (174 HGSOC with proteomics, phosphoproteomics,
RNA, methylation, WSI, CT) is underutilised. No published tool systematically
integrates WGS + RNA + methylation + proteomics + imaging for HRD.

**Baseline in repo:** none. Only VCF-level features.

**What to add:**
- Modality adapters: WSI (UNI2 or Virchow2), RNA-seq (transformer encoder or
  Geneformer/scGPT), methylation (MLP), proteomics (MLP)
- Fusion backbone: SurvPath-style cross-attention or a simple late-fusion MLP
- Training cohort: CPTAC-OV (174) + TCGA-BRCA/OV
- UI: "What other data do you have?" wizard that accepts optional modalities

### 6. RAD51 foci deep-learning pipeline

**Claim:** RAD51 foci assay (VHIO, NKI RECAP, Konstantinopoulos FFPE-compatible)
has 15-30% failure rates and manual scoring. MAP-HR (Sullivan 2025) achieves
DICE 0.74-0.80 on public IDR + BBBC image sets — beatable with transformer
detectors + Cellpose-SAM nucleus masks.

**Baseline in repo:** none. No image ingestion.

**What to add:**
- Separate from the main app; a CLI tool (`tools/rad51_foci_segmenter/`) that
  wraps Cellpose-SAM + StarDist + a U-Net puncta head
- Results feed back into the HRD card as a "Functional HRD" layer alongside
  the scar layer

### 7. Time-series transformer on serial ctDNA

**Claim:** Temporal Fusion Transformer or Neural ODEs predicting time-to-
resistance from serial ctDNA would fill an under-served monitoring niche.

**Baseline in repo:** none.

**What to add:**
- Longitudinal ctDNA data model + time-series transformer
- Integration with DARC-Sign (De Sarkar 2023) as a multi-class resistance predictor
- This probably stays offline / research-grade until real longitudinal data lands

### 8. Mutation-level foundation model (SigFM)

**Claim:** No pretrained foundation model exists on mutational spectra at cohort
scale. Pretraining a MuAt-style attention architecture with masked mutation
modeling on ~50,000 combined PCAWG + Hartwig + 100,000 Genomes WGS, fine-tuned
to HRD / MSI / tissue-of-origin / PARPi response, would be a defensible novel
contribution.

**Baseline in repo:** none.

**What to add:**
- Separate training pipeline — big-compute, probably Modal A100 cluster
- Ships as a downloadable `sigfm-v1` model artefact consumed by the existing
  `services/analysis.py` as an optional signal

### 9. Ancestry-robust HRD classifier

**Claim:** TCGA-BRCA is ~77% European, ~12% African, <1% South Asian. African-
ancestry tumors show higher genomic instability and HRD prevalence but are
under-represented in training. PhyloFrame (Jaggers & Greene, *Nat Comms* 2025)
demonstrates ancestry-aware transcriptomic bias correction.

**Baseline in repo:** none. All training sets skew European.

**What to add:**
- Ancestry metadata ingestion from TCGA / Hartwig / 100kGP
- PhyloFrame-style re-weighting or domain-adversarial training
- Evaluation slice: per-ancestry AUROC + calibration plots
- README: per-ancestry reporting as a model card

### 10. Public HRD benchmark suite

**Claim:** No unified public benchmark with leaderboard and standardised
evaluation exists. Friends of Cancer Research identified the gap explicitly.

**Baseline in repo:** none.

**What to add:**
- `benchmarks/hrd-suite/` — datasets, eval scripts, leaderboard CSV, CI that
  runs every model against the suite on each commit
- TRIPOD+AI and PROBAST+AI compliance checklists per entry

### 11. Causal-inference model for PARPi CATE

**Claim:** Use GENIE BPC or Flatiron-Foundation CGDB with EconML/DML to estimate
per-patient PARP-inhibitor treatment effects conditional on features.

**Baseline in repo:** none.

**What to add:**
- `apps/api/src/api/ml/cate.py` — EconML or CausalML DoubleML estimator
- UI: "estimated survival benefit from PARPi for your profile" with uncertainty
  intervals
- Heavy methodological disclaimers — CATE from observational data is fraught

## Reporting standards

Any model added under this roadmap must be documented per:

- **TRIPOD+AI** (Collins et al., *BMJ* 2024, 27-item checklist)
- **PROBAST+AI** (2025 risk-of-bias tool)
- **CLAIM 2.0** for imaging models
- **MI-CLAIM** for clinical AI modelling
- Explicit per-ancestry + per-institution performance reporting
- External validation on at least one cohort not used in training

## What would make this project credible to the field

The HRD Harmonization Project and the DeepHRD-PAOLA-1 collapse (AUC 0.81 → 0.57)
make one point loud and clear: the field is drowning in internal-validation
numbers and starving for honest external-validation evidence. The single most
valuable contribution is not another high TCGA AUROC — it's rigorous reporting
(TRIPOD+AI), transparent failure modes, ancestry-stratified performance, and
documented drift when the same model runs on CPTAC, PAOLA-1, Hartwig, and 100kGP.

That methodological honesty is the differentiating signal and the thing the
research engineering in this repo should optimise for.

## References

Key papers referenced:

- Findlay GM, Daza RM, Martin B, et al. *Accurate classification of BRCA1
  variants with saturation genome editing.* Nature 2018.
- Huang H, et al. *BRCA2 functional variants via saturation genome editing.*
  Nature 2024-2025.
- Bergstrom EN et al. *DeepHRD.* JCO 2024.
- Wagener-Ryczek S et al. *DeepHRD PAOLA-1 validation.* Eur J Cancer 2025.
- Sanjaya & Pitkänen. *MuAt: mutation attention.* Genome Medicine 2023.
- De Sarkar N et al. *DARC-Sign.* npj Genomic Medicine 2023.
- Silverman C, Schonhoft J et al. *HRD reversions on PARPi.* Clin Cancer Res 2025.
- Weir A et al. *IdentifiHR.* Communications Medicine 2026.
- Sosinsky A et al. *100,000 Genomes Project HRD analysis.* Nat Med 2024.
- Sztupinszki Z et al. *scarHRD R package.* npj Breast Cancer 2018.
- Davies H et al. *HRDetect.* Nat Med 2017.
- Friends of Cancer Research HRD Harmonization Project white paper, 2024.
- Jaggers S & Greene CS. *PhyloFrame.* Nat Commun 2025.
- Ziogas DC et al. *AlphaMissense performance on HR variants.* npj Precis Oncol 2024.
- Niu Y et al. *AlphaMissense variant classification.* JCO Precis Oncol 2025.
- Collins GS et al. *TRIPOD+AI.* BMJ 2024.
