"""BRCA1 variant-effect classifier (Tier 3).

Model layer trained on saturation genome editing (SGE) functional scores from
Findlay et al. 2018 (Nature 562, 217–222). The original assay depletes HAP1-
Lig4KO cells carrying each of 3,893 BRCA1 single-nucleotide variants and reads
out functional effect on homologous recombination via a DNA-damage selection.

This module owns:
  - data/findlay_brca1_2018.xlsx  — raw supplementary table, checked in
  - train.py                      — feature engineering + XGBoost training
  - infer.py                      — load the saved model and predict on one variant
  - models/brca1_xgb_v1.json      — the serialized model (produced by train.py)

The model is a research-grade v0 — useful for triage, NOT a substitute for
ENIGMA expert classification or genetic counseling.
"""
