"""Filter a VCF to PASS variants at catalog loci (± 1kb flanking).

Keeps records that:
  1. have FILTER == PASS (or missing FILTER)
  2. sit at or very near a coordinate our catalog cares about

This is the "region of interest" pre-filter any clinical variant pipeline
runs before annotation. The flanking window lets downstream steps pick up
linked variants (e.g. the two rsIDs that jointly define TPMT*3A).
"""

import logging
import sys
from pathlib import Path

from cyvcf2 import VCF, Writer

# Catalog coordinate list. Duplicates api.services.vcf._COORDS intentionally,
# because the pipeline is designed to run standalone without the full API
# package installed. Keeping these in sync is on us; a production codebase
# would import from one shared module and use that for both.
CATALOG_LOCI: list[tuple[str, int]] = [
    ("22", 42128945),   # CYP2D6*4 (rs3892097)
    ("1",  97573863),   # DPYD*2A (rs3918290)
    ("1",  97450058),   # DPYD c.2846A>T (rs67376798)
    ("6",  18139228),   # TPMT*3A marker (rs1800460)
    ("6",  18130918),   # TPMT*3A marker (rs1142345)
    ("6",  18143955),   # TPMT*2 (rs1800462)
    ("17", 43124097),   # BRCA1 p.Cys61Gly (c.181T>G)
]
FLANK = 1000  # bp window around each locus to keep, for linked SNPs


snakemake = globals()["snakemake"]  # type: ignore[name-defined]
inp: str = snakemake.input.vcf
out: str = snakemake.output.vcf
log_path: str = snakemake.log[0]


def _norm_chrom(c: str) -> str:
    return c[3:] if c.startswith("chr") else c


def _in_any_window(chrom: str, pos: int) -> bool:
    return any(
        chrom == c and abs(pos - p) <= FLANK
        for c, p in CATALOG_LOCI
    )


def main() -> int:
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    vcf = VCF(inp)
    writer = Writer(out, vcf)

    total = 0
    kept = 0
    dropped_filter = 0
    dropped_region = 0

    for rec in vcf:
        total += 1
        filt = rec.FILTER or "PASS"
        if filt != "PASS":
            dropped_filter += 1
            continue
        if not _in_any_window(_norm_chrom(rec.CHROM), rec.POS):
            dropped_region += 1
            continue
        writer.write_record(rec)
        kept += 1

    writer.close()
    vcf.close()
    logging.info(
        "filter_catalog: %d in, %d kept (%d failed FILTER, %d outside catalog regions)",
        total, kept, dropped_filter, dropped_region,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
