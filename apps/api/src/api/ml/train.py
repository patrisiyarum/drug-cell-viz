"""Train BRCA1 variant-effect models on Findlay 2018 SGE data.

Run with:
    uv run python -m api.ml.train

Produces three artifacts in models/:
  - brca1_xgb_v1.json                     XGBoost binary classifier (LOF vs FUNC)
  - brca1_ensemble_v1.json                Logistic meta-learner over [XGB score, AlphaMissense]
  - brca1_xgb_v1_metadata.json            Held-out metrics + conformal thresholds

Pipeline:
  1. Load Findlay SGE labels, drop intermediate-class variants.
  2. Featurize (position/domain/AA-properties — see features.py).
  3. Train/test/calibration split: 60/20/20 stratified by label.
  4. Train XGBoost on the 60% train set.
  5. Evaluate XGBoost on held-out test (20%).
  6. Evaluate AlphaMissense on held-out test (where AM has a score).
  7. Build an ensemble: logistic regression on [xgb_proba, am_proba] fit on
     the 20% calibration split.
  8. Evaluate ensemble on held-out test.
  9. Compute split-conformal thresholds for the ensemble on the calibration
     split. Uses absolute residual |y - p| as the nonconformity score.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from api.ml import alphamissense as am
from api.ml.features import DOMAINS, feature_names, featurize_one

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
DATA_PATH = HERE / "data" / "findlay_brca1_2018.xlsx"
MODEL_PATH = HERE / "models" / "brca1_xgb_v1.json"
ENSEMBLE_PATH = HERE / "models" / "brca1_ensemble_v1.json"
META_PATH = HERE / "models" / "brca1_xgb_v1_metadata.json"


def load_findlay() -> pd.DataFrame:
    df = pd.read_excel(DATA_PATH, header=2)
    keep = [
        "gene",
        "position (hg19)",
        "aa_pos",
        "aa_ref",
        "aa_alt",
        "protein_variant",
        "consequence",
        "function.score.mean",
        "func.class",
        "clinvar_simple",
    ]
    return df[keep].copy()


def _am_scores_for(df_: pd.DataFrame) -> np.ndarray:
    """Vector of AlphaMissense scores aligned with df_. NaN where AM has none."""
    out = np.full(len(df_), np.nan, dtype=np.float32)
    for i, (_, row) in enumerate(df_.iterrows()):
        if pd.notna(row["aa_ref"]) and pd.notna(row["aa_alt"]) and pd.notna(row["aa_pos"]):
            got = am.lookup(str(row["aa_ref"]), int(row["aa_pos"]), str(row["aa_alt"]))
            if got is not None:
                out[i] = got[0]
    return out


def _conformal_thresholds(y: np.ndarray, p: np.ndarray, coverages: list[float]) -> dict[float, float]:
    """Split-conformal nonconformity thresholds.

    Nonconformity score = |y_true - p_LOF|. For a requested coverage 1-alpha,
    the threshold q is the (1-alpha) * (1 + 1/n) empirical quantile of
    nonconformities on the calibration set. At test time we construct the
    interval as [p - q, p + q] clipped to [0, 1]; a point is "LOF" at coverage
    1-alpha iff the interval lies strictly above 0.5.
    """
    scores = np.abs(y.astype(float) - p)
    n = len(scores)
    out: dict[float, float] = {}
    for cov in coverages:
        level = np.ceil((n + 1) * cov) / n
        level = float(min(level, 1.0))
        out[cov] = float(np.quantile(scores, level, method="higher"))
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    df = load_findlay()
    logger.info("loaded %d SNVs from Findlay 2018", len(df))

    df = df[df["func.class"].isin(["LOF", "FUNC"])].copy()
    df["y"] = (df["func.class"] == "LOF").astype(int)
    logger.info(
        "after filtering INT: %d rows (LOF=%d, FUNC=%d)",
        len(df),
        int(df["y"].sum()),
        int((df["y"] == 0).sum()),
    )

    X = np.vstack(
        [
            featurize_one(
                row["aa_pos"] if pd.notna(row["aa_pos"]) else None,
                row["aa_ref"] if pd.notna(row["aa_ref"]) else None,
                row["aa_alt"] if pd.notna(row["aa_alt"]) else None,
                row["consequence"] if pd.notna(row["consequence"]) else None,
            )
            for _, row in df.iterrows()
        ]
    )
    y = df["y"].values.astype(int)
    feats = feature_names()

    # 60/20/20 split: train, calibration (for ensemble + conformal), test.
    X_tr, X_rest, y_tr, y_rest, df_tr, df_rest = train_test_split(
        X, y, df, test_size=0.40, random_state=42, stratify=y
    )
    X_cal, X_te, y_cal, y_te, df_cal, df_te = train_test_split(
        X_rest, y_rest, df_rest, test_size=0.50, random_state=42, stratify=y_rest
    )
    logger.info("train=%d cal=%d test=%d", len(y_tr), len(y_cal), len(y_te))

    # --- Step 1: XGBoost ---
    clf = xgb.XGBClassifier(
        n_estimators=400, max_depth=5, learning_rate=0.05,
        subsample=0.9, colsample_bytree=0.9,
        reg_alpha=0.1, reg_lambda=1.0,
        random_state=42, tree_method="hist", eval_metric="logloss",
    )
    clf.fit(X_tr, y_tr)

    xgb_test = clf.predict_proba(X_te)[:, 1]
    xgb_cal = clf.predict_proba(X_cal)[:, 1]
    xgb_test_metrics = _metrics("xgb_only", y_te, xgb_test)

    # --- Step 2: AlphaMissense standalone ---
    am_test = _am_scores_for(df_te)
    am_cal = _am_scores_for(df_cal)

    am_mask_test = ~np.isnan(am_test)
    am_cov_test = int(am_mask_test.sum())
    logger.info("AlphaMissense covers %d/%d test variants", am_cov_test, len(y_te))
    if am_mask_test.sum() > 0:
        am_only_metrics = _metrics(
            "alphamissense_only",
            y_te[am_mask_test],
            am_test[am_mask_test],
        )
    else:
        am_only_metrics = {"auroc": None, "auprc": None, "brier": None, "n": 0}

    # --- Step 3: Ensemble (logistic meta-learner on [xgb, am]) ---
    # For variants AlphaMissense doesn't cover (synonymous, rare edge cases),
    # we impute the missing AM score with the calibration-set mean. That way
    # the ensemble still fires end-to-end.
    am_cal_fill = np.where(np.isnan(am_cal), np.nanmean(am_cal), am_cal)
    am_test_fill = np.where(np.isnan(am_test), np.nanmean(am_cal), am_test)

    meta_X_cal = np.column_stack([xgb_cal, am_cal_fill])
    meta = LogisticRegression(max_iter=500).fit(meta_X_cal, y_cal)
    logger.info("ensemble weights: xgb=%.3f am=%.3f intercept=%.3f",
                meta.coef_[0, 0], meta.coef_[0, 1], meta.intercept_[0])

    meta_X_te = np.column_stack([xgb_test, am_test_fill])
    ens_test = meta.predict_proba(meta_X_te)[:, 1]
    ens_metrics = _metrics("ensemble", y_te, ens_test)

    # --- Step 4: Conformal calibration on the ensemble ---
    ens_cal = meta.predict_proba(meta_X_cal)[:, 1]
    conformal_q = _conformal_thresholds(y_cal, ens_cal, coverages=[0.80, 0.90, 0.95])
    logger.info("conformal thresholds (|y - p_LOF|): %s", conformal_q)

    # --- Per-domain breakdown on the ensemble ---
    per_domain = {}
    for dname, (lo, hi) in DOMAINS.items():
        mask = df_te["aa_pos"].fillna(-1).astype(float).between(lo, hi)
        if mask.sum() < 20 or len(np.unique(y_te[mask.values])) < 2:
            continue
        per_domain[dname] = {
            "n": int(mask.sum()),
            "ensemble_auroc": float(roc_auc_score(y_te[mask.values], ens_test[mask.values])),
            "xgb_auroc": float(roc_auc_score(y_te[mask.values], xgb_test[mask.values])),
            "positive_rate": float(y_te[mask.values].mean()),
        }
    logger.info("per-domain: %s", per_domain)

    # --- Persist everything ---
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    clf.save_model(str(MODEL_PATH))

    # Logistic meta is tiny — store as JSON so we don't need joblib on the
    # inference side.
    ENSEMBLE_PATH.write_text(
        json.dumps(
            {
                "coef": meta.coef_[0].tolist(),
                "intercept": float(meta.intercept_[0]),
                "feature_order": ["xgb_proba_lof", "alphamissense_pathogenicity"],
                "am_fill_value": float(np.nanmean(am_cal)),
            },
            indent=2,
        )
    )

    importances = dict(
        sorted(
            zip(feats, clf.feature_importances_.tolist()),
            key=lambda t: t[1],
            reverse=True,
        )[:20]
    )

    metadata = {
        "model_version": "brca1_xgb_v1",
        "trained_on": "Findlay et al. 2018 (Nature, doi:10.1038/s41586-018-0461-z)",
        "training_citation": "Findlay GM, Daza RM, Martin B, et al. Accurate classification of BRCA1 variants with saturation genome editing. Nature 562, 217-222 (2018).",
        "task": "binary classification: LOF vs FUNC (intermediate variants excluded from training)",
        "train_size": int(len(y_tr)),
        "calibration_size": int(len(y_cal)),
        "test_size": int(len(y_te)),
        "holdout_metrics": ens_metrics,  # headline = ensemble
        "baseline_metrics": {
            "xgb_only": xgb_test_metrics,
            "alphamissense_only": am_only_metrics,
        },
        "alphamissense_coverage_on_test": {
            "covered": am_cov_test,
            "total": int(len(y_te)),
            "fraction": am_cov_test / max(1, len(y_te)),
        },
        "ensemble_weights": {
            "xgb": float(meta.coef_[0, 0]),
            "alphamissense": float(meta.coef_[0, 1]),
            "intercept": float(meta.intercept_[0]),
            "am_imputation_value_for_missing": float(np.nanmean(am_cal)),
            "attribution": "AlphaMissense: DeepMind, Science 2023 (doi:10.1126/science.adg7492). CC BY-NC-SA 4.0.",
        },
        "conformal": {
            "method": "split-conformal on absolute residual |y - p_LOF|",
            "calibration_n": int(len(y_cal)),
            "thresholds": conformal_q,
        },
        "per_domain_auroc": per_domain,
        "top_features": importances,
        "feature_count": len(feats),
        "feature_names": feats,
    }
    META_PATH.write_text(json.dumps(metadata, indent=2))
    logger.info("saved model to %s, ensemble to %s, metadata to %s",
                MODEL_PATH, ENSEMBLE_PATH, META_PATH)


def _metrics(name: str, y: np.ndarray, p: np.ndarray) -> dict:
    preds = (p >= 0.5).astype(int)
    auroc = float(roc_auc_score(y, p))
    auprc = float(average_precision_score(y, p))
    brier = float(brier_score_loss(y, p))
    cm = confusion_matrix(y, preds).tolist()
    logger.info("%-20s AUROC=%.3f AUPRC=%.3f Brier=%.3f n=%d", name, auroc, auprc, brier, len(y))
    return {
        "auroc": auroc,
        "auprc": auprc,
        "brier": brier,
        "confusion_matrix": cm,
        "positive_rate": float(y.mean()),
        "n": int(len(y)),
    }


if __name__ == "__main__":
    main()
