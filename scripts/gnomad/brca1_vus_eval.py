"""Run every BRCA1 missense in the gnomAD slice through the ML classifier,
emit a CSV of predictions + any ENIGMA labels we have.

This is the concrete test of the BRCA1 classifier's real-world behaviour:
does it produce well-calibrated scores on variants it's never seen, and do
its calls agree with ENIGMA for the variants ENIGMA has reviewed?

Expected runtime on 1,000 BRCA1 variants: ~3 minutes (cached AlphaFold +
AlphaMissense lookups) on a warm API.
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

import requests

logger = logging.getLogger("brca1_vus_eval")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gnomad", required=True, type=Path)
    p.add_argument("--api", default="http://localhost:8000",
                   help="Base URL of the running drug-cell-viz API")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--limit", type=int, default=None,
                   help="Only score first N variants (debug)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        from cyvcf2 import VCF
    except ImportError:
        logger.error("cyvcf2 required — `uv sync --extra pipeline --package api`")
        return 2

    vcf = VCF(str(args.gnomad))
    args.out.parent.mkdir(parents=True, exist_ok=True)

    n_scored = 0
    with args.out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "chrom", "pos", "ref", "alt", "gene", "hgvs_protein",
            "gnomad_af", "gnomad_af_popmax",
            "clinvar_significance", "enigma_classification",
            "p_loss_of_function", "model_label", "model_confidence",
            "conformal_80_label", "conformal_80_singleton",
        ])

        for rec in vcf:
            # We only want BRCA1 + missense records. gnomAD's VEP INFO includes
            # the protein consequence (HGVSp) and the gene symbol.
            csq = rec.INFO.get("vep") or rec.INFO.get("CSQ") or ""
            if "BRCA1" not in csq:
                continue
            if "missense_variant" not in csq:
                continue

            hgvsp = _parse_hgvsp_from_csq(csq)
            if hgvsp is None:
                continue

            # ClinVar significance if gnomAD has it inlined.
            clinvar_sig = _first_info(rec, ["ClinVar_significance", "clinvar_clnsig"])

            # Ask the API.
            try:
                resp = requests.post(
                    f"{args.api}/api/brca1/classify",
                    json={"hgvs_protein": hgvsp},
                    timeout=30,
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:
                logger.warning("classify %s failed: %s", hgvsp, exc)
                continue

            # Ask BRCA Exchange for an ENIGMA opinion.
            enigma = None
            try:
                r = requests.get(
                    f"{args.api}/api/brca1/exchange",
                    params={"hgvs_protein": hgvsp},
                    timeout=30,
                )
                if r.ok and r.json():
                    enigma = r.json().get("enigma_classification")
            except Exception:
                pass

            af = rec.INFO.get("AF")
            af_popmax = rec.INFO.get("AF_popmax") or rec.INFO.get("popmax_AF")
            conformal = payload.get("conformal") or {}
            writer.writerow([
                rec.CHROM, rec.POS, rec.REF, rec.ALT[0] if rec.ALT else "",
                "BRCA1", hgvsp,
                af, af_popmax,
                clinvar_sig, enigma,
                payload.get("probability_loss_of_function"),
                payload.get("label"),
                payload.get("confidence"),
                conformal.get("label"),
                len(conformal.get("prediction_set", [])) == 1,
            ])
            n_scored += 1
            if n_scored % 50 == 0:
                logger.info("scored %d variants", n_scored)
            if args.limit and n_scored >= args.limit:
                break

    logger.info("wrote %d rows to %s", n_scored, args.out)
    return 0


def _parse_hgvsp_from_csq(csq: str) -> str | None:
    """VEP CSQ is `|`-separated; 11th field is HGVSp like 'p.Cys61Gly'."""
    for entry in csq.split(","):
        fields = entry.split("|")
        for f in fields:
            if f.startswith("ENSP") and ":" in f:
                # 'ENSP00000351547.3:p.Cys61Gly' → 'p.Cys61Gly'
                return f.split(":", 1)[1]
            if f.startswith("p."):
                return f
    return None


def _first_info(rec, keys: list[str]) -> str | None:
    for k in keys:
        v = rec.INFO.get(k)
        if v is not None and v != "":
            return str(v)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
