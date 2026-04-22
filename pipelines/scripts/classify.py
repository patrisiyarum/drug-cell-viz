"""Classify: match records to catalog variants + run the analysis pipeline.

This is where the pharmacogenomic evidence and the ML variant-effect
classifier meet. It imports `api.services.vcf` + `api.services.analysis`
directly, so the pipeline's results match what the live API would return.
"""

import asyncio
import csv
import json
import logging
import sys
from pathlib import Path

# Make the api package importable when running under snakemake.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api" / "src"))

from api.services import analysis as analysis_service  # noqa: E402
from api.services import vcf as vcf_service             # noqa: E402


snakemake = globals()["snakemake"]  # type: ignore[name-defined]
inp: str = snakemake.input.vcf
out_detections: str = snakemake.output.detections
out_classifications: str = snakemake.output.classifications
out_json: str = snakemake.output.json_report
log_path: str = snakemake.log[0]
sample_name: str = snakemake.params.sample
drug_id: str = snakemake.params.drug_id


def main() -> int:
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.info("classify: sample=%s drug=%s", sample_name, drug_id)

    # Step 1: catalog matches via cyvcf2.
    result = vcf_service.ingest(Path(inp))
    logging.info(
        "ingest: %d records, %d detections, sample=%s",
        result.total_records,
        len(result.detections),
        result.analyzed_sample,
    )

    # Step 2: detections.tsv — one row per match.
    with open(out_detections, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(
            [
                "sample", "catalog_id", "gene", "display_name",
                "chrom", "pos", "ref", "alt", "zygosity", "vcf_filter",
            ]
        )
        for d in result.detections:
            w.writerow(
                [
                    sample_name, d.catalog_id, d.gene, d.display_name,
                    d.chrom, d.pos, d.ref, d.alt, d.zygosity, d.vcf_filter,
                ]
            )

    # Step 3: analysis (drug × variants) — same pipeline the API runs.
    variants = vcf_service.detections_to_variant_inputs(result.detections)
    analysis = None
    if variants:
        try:
            analysis = asyncio.run(
                analysis_service.run_analysis(drug_id, variants),
            )
        except Exception as exc:
            logging.exception("run_analysis failed: %s", exc)

    # Step 4: classifications.tsv — one row per BRCA1 variant the ML model saw.
    with open(out_classifications, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(
            [
                "sample", "hgvs_protein", "model_version",
                "probability_loss_of_function", "label",
                "confidence", "in_assayed_region", "domain",
            ]
        )
        if analysis is not None:
            for hgvs in analysis.classifiable_brca1_variants:
                pred = _classify_brca1(hgvs)
                if pred is None:
                    continue
                w.writerow(
                    [
                        sample_name,
                        hgvs,
                        pred["model_version"],
                        pred["probability_loss_of_function"],
                        pred["label"],
                        pred["confidence"],
                        pred["in_assayed_region"],
                        pred["domain"],
                    ]
                )

    # Step 5: report.json — full structured output.
    report = {
        "sample": sample_name,
        "drug_id": drug_id,
        "vcf": {
            "path": inp,
            "total_records": result.total_records,
            "records_pass": result.records_pass,
            "analyzed_sample": result.analyzed_sample,
        },
        "detections": [
            {
                "catalog_id": d.catalog_id,
                "gene": d.gene,
                "display_name": d.display_name,
                "chrom": d.chrom,
                "pos": d.pos,
                "ref": d.ref,
                "alt": d.alt,
                "zygosity": d.zygosity,
                "vcf_filter": d.vcf_filter,
            }
            for d in result.detections
        ],
        "analysis": analysis.model_dump(mode="json") if analysis else None,
    }
    with open(out_json, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logging.info("wrote %s, %s, %s", out_detections, out_classifications, out_json)
    return 0


def _classify_brca1(hgvs: str) -> dict | None:
    from api.ml.infer import classify as brca1_classify, parse_hgvs_protein

    try:
        ref, pos, alt = parse_hgvs_protein(hgvs)
    except Exception:
        return None
    r = brca1_classify(ref, pos, alt)
    return {
        "model_version": "brca1_xgb_v1",
        "probability_loss_of_function": r["probability_loss_of_function"],
        "label": r["label"],
        "confidence": r["confidence"],
        "in_assayed_region": r["in_assayed_region"],
        "domain": r["domain"],
    }


if __name__ == "__main__":
    sys.exit(main())
