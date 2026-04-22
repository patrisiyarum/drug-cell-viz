"""Render a human-readable text report from the JSON output of `classify`.

Designed so a clinician or patient can read the full report without any
tooling beyond `less` / `cat`. Every line cites its source.
"""

import json
import sys
from pathlib import Path

snakemake = globals()["snakemake"]  # type: ignore[name-defined]
inp: str = snakemake.input.json_report
out: str = snakemake.output.txt


def main() -> int:
    report = json.loads(Path(inp).read_text())
    lines: list[str] = []

    drug = report.get("drug_id", "?")
    sample = report.get("sample", "?")
    lines.append("=" * 72)
    lines.append(f"drug-cell-viz variant report")
    lines.append(f"sample : {sample}")
    lines.append(f"drug   : {drug}")
    lines.append("=" * 72)
    lines.append("")

    vcf_stats = report.get("vcf") or {}
    lines.append(
        f"VCF summary: {vcf_stats.get('total_records', 0)} records, "
        f"{vcf_stats.get('records_pass', 0)} PASS. "
        f"Analyzed sample: {vcf_stats.get('analyzed_sample', '?')}"
    )
    lines.append("")

    # Detections.
    detections = report.get("detections") or []
    lines.append(f"Detected catalog variants: {len(detections)}")
    lines.append("-" * 72)
    for d in detections:
        lines.append(
            f"  {d['display_name']:45s}  {d['zygosity']:13s}  "
            f"chr{d['chrom']}:{d['pos']} {d['ref']}>{d['alt']}"
        )
    lines.append("")

    # PGx verdicts.
    analysis = report.get("analysis") or {}
    verdicts = analysis.get("pgx_verdicts") or []
    lines.append(f"Pharmacogenomic verdicts: {len(verdicts)}")
    lines.append("-" * 72)
    for v in verdicts:
        lines.append(f"  [{v['evidence_level']}] {v['drug_name']} × {v['variant_label']}")
        lines.append(f"      phenotype: {v['phenotype']}")
        lines.append(f"      {v['recommendation']}")
        lines.append(f"      source: {v['source']}")
        lines.append("")

    if analysis.get("headline"):
        lines.append("Bottom line:")
        lines.append(f"  {analysis['headline']}")
        lines.append(f"  (severity: {analysis.get('headline_severity', '?')})")
        lines.append("")

    brca1 = analysis.get("classifiable_brca1_variants") or []
    if brca1:
        lines.append(f"BRCA1 variants sent to ML classifier: {len(brca1)}")
        for h in brca1:
            lines.append(f"  {h}")
        lines.append("(see classifications.tsv for per-variant predictions)")
        lines.append("")

    lines.append("=" * 72)
    lines.append("Educational use only. Not a medical device. Consult a qualified")
    lines.append("oncologist and a clinical pharmacogenomicist before any treatment")
    lines.append("decision. Genetic testing must be performed by a CLIA-certified lab.")
    lines.append("=" * 72)

    Path(out).write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
