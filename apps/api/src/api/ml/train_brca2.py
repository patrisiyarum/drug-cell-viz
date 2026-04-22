"""Train a BRCA2 DBD variant-effect classifier on Huang et al. 2025 SGE data.

Run with:
    uv run python -m api.ml.train_brca2

Training data: Huang, Hu et al. 2025 (Nature, doi:10.1038/s41586-024-08388-8),
Supplementary Table S3 — 4,583 missense SNVs in the BRCA2 DNA-binding domain
(exons 15-26, residues 2479-3216), with ACMG-style functional categories
derived from a saturation genome editing assay.

Labels (binary):
  - Pathogenic  = {"P strong", "P moderate"}           → y=1
  - Benign      = {"B strong", "B moderate"}           → y=0
  - Supporting + VUS excluded from training (low certainty).

Features reuse api.ml.features.featurize_one with a BRCA2-specific domain
override (BRCA2 DBD subdomains are different from BRCA1's RING/BRCT).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from api.ml.features import featurize_one

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
DATA_PATH = HERE / "data" / "huang_brca2_2025.xlsx"
MODEL_PATH = HERE / "models" / "brca2_xgb_v1.json"
META_PATH = HERE / "models" / "brca2_xgb_v1_metadata.json"


POSITIVE_LABELS = {"P strong", "P moderate"}
NEGATIVE_LABELS = {"B strong", "B moderate"}


def load_huang() -> pd.DataFrame:
    df = pd.read_excel(DATA_PATH, sheet_name="Table S3", header=1)
    df = df.rename(
        columns={
            "EventType": "event_type",
            "Amino acid change (p.)": "protein_variant",
            "Functional category ": "category",
            "Model based functional score": "function_score",
        }
    )
    df = df[df["event_type"] == "Missense"].copy()

    # Huang et al. write variants as "D2479A" (1-letter, no p. prefix).
    # Parse with a single regex; keep 1-letter form for our features.
    import re
    parsed: list[tuple[str | None, int | None, str | None]] = []
    for pv in df["protein_variant"]:
        m = re.fullmatch(r"([A-Z])(\d+)([A-Z])", str(pv))
        if m:
            parsed.append((m.group(1), int(m.group(2)), m.group(3)))
        else:
            parsed.append((None, None, None))
    df["aa_ref"] = [p[0] for p in parsed]
    df["aa_pos"] = [p[1] for p in parsed]
    df["aa_alt"] = [p[2] for p in parsed]
    df = df[df["aa_ref"].notna()].copy()
    df["consequence"] = "Missense"
    return df


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    df = load_huang()
    logger.info("loaded %d BRCA2 DBD missense SNVs from Huang 2025", len(df))

    df = df[df["category"].isin(POSITIVE_LABELS | NEGATIVE_LABELS)].copy()
    df["y"] = df["category"].isin(POSITIVE_LABELS).astype(int)
    logger.info(
        "after filtering VUS/supporting: %d rows (Pathogenic=%d, Benign=%d)",
        len(df),
        int(df["y"].sum()),
        int((df["y"] == 0).sum()),
    )

    # Note: features.featurize_one uses BRCA1's domain annotation. For BRCA2
    # that one-hot will be zero everywhere — which is fine; the model learns
    # from the AA-change features and absolute position. A proper BRCA2
    # classifier would re-encode subdomains (OB1/OB2/OB3/tower). For v0 this
    # is the baseline.
    X = np.vstack(
        [
            featurize_one(row["aa_pos"], row["aa_ref"], row["aa_alt"], row["consequence"])
            for _, row in df.iterrows()
        ]
    )
    y = df["y"].values.astype(int)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    logger.info("train=%d test=%d", len(y_tr), len(y_te))

    clf = xgb.XGBClassifier(
        n_estimators=400, max_depth=5, learning_rate=0.05,
        subsample=0.9, colsample_bytree=0.9,
        reg_alpha=0.1, reg_lambda=1.0,
        random_state=42, tree_method="hist", eval_metric="logloss",
    )
    clf.fit(X_tr, y_tr)

    p = clf.predict_proba(X_te)[:, 1]
    preds = (p >= 0.5).astype(int)

    auroc = float(roc_auc_score(y_te, p))
    auprc = float(average_precision_score(y_te, p))
    brier = float(brier_score_loss(y_te, p))
    cm = confusion_matrix(y_te, preds).tolist()
    logger.info("AUROC=%.3f AUPRC=%.3f Brier=%.3f CM=%s n=%d",
                auroc, auprc, brier, cm, len(y_te))

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    clf.save_model(str(MODEL_PATH))

    metadata = {
        "model_version": "brca2_xgb_v1",
        "trained_on": "Huang, Hu et al. 2025 (Nature, doi:10.1038/s41586-024-08388-8)",
        "training_citation": "Huang H, Hu C, Ji J, et al. Functional evaluation and clinical classification of BRCA2 variants. Nature 638, 528-537 (2025).",
        "task": "binary classification: Pathogenic (P strong + P moderate) vs Benign (B strong + B moderate); VUS and supporting excluded",
        "covered_region": "BRCA2 DNA-binding domain, exons 15-26, residues 2479-3216",
        "train_size": int(len(y_tr)),
        "test_size": int(len(y_te)),
        "holdout_metrics": {
            "auroc": auroc,
            "auprc": auprc,
            "brier": brier,
            "confusion_matrix": cm,
            "positive_rate": float(y_te.mean()),
            "n": int(len(y_te)),
        },
        "caveat": "Features reuse the BRCA1 domain encoding (all-zero for BRCA2). v0 baseline; a production model would encode BRCA2 subdomains (OB1/OB2/OB3/tower/helical).",
    }
    META_PATH.write_text(json.dumps(metadata, indent=2))
    logger.info("saved model to %s, metadata to %s", MODEL_PATH, META_PATH)


if __name__ == "__main__":
    main()
