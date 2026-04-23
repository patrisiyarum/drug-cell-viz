"""Validate that every curated catalog variant maps to a real gnomAD record.

Reads gnomAD's HR-panel slice and `api.services.bc_catalog.VARIANTS`; for each
catalog entry, tries to find a matching gnomAD record at the expected chrom/pos
with the expected ref/alt alleles. Prints a coverage report — coordinates that
don't match are likely bugs in the catalog or version-skew between the catalog's
assumed coordinates and the deployed reference build.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger("validate_catalog")


# Gene coordinates (GRCh38) we expect each catalog variant to land in. Used
# as a sanity check before we even hit the gnomAD VCF.
GENE_COORDS = {
    "BRCA1":  ("chr17", 43_044_295, 43_125_483),
    "BRCA2":  ("chr13", 32_315_474, 32_400_266),
    "PALB2":  ("chr16", 23_603_160, 23_641_310),
    "ATM":    ("chr11", 108_222_832, 108_369_102),
    "CHEK2":  ("chr22", 28_687_820, 28_741_585),
    "RAD51C": ("chr17", 58_692_573, 58_735_461),
    "RAD51D": ("chr17", 35_101_353, 35_119_221),
    "BRIP1":  ("chr17", 61_679_193, 61_863_563),
    "BARD1":  ("chr2",  214_725_646, 214_808_175),
    "PARP1":  ("chr1",  226_360_251, 226_408_154),
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gnomad", required=True, type=Path,
                   help="Path to the HR-panel gnomAD VCF (produced by extract_hr_panel.sh)")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    logging.basicConfig(level=args.log_level, format="%(message)s")

    # Deferred import so the script is runnable outside the api env.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/api/src"))
    from api.services.bc_catalog import VARIANTS

    try:
        from cyvcf2 import VCF
    except ImportError:
        logger.error("cyvcf2 required — run `uv sync --extra pipeline --package api`")
        return 2

    vcf = VCF(str(args.gnomad))
    seen_sites: set[tuple[str, int, str, str]] = set()
    for rec in vcf:
        for alt in rec.ALT:
            seen_sites.add((rec.CHROM, int(rec.POS), rec.REF, alt))

    logger.info("loaded %d unique gnomAD sites across the HR panel", len(seen_sites))

    checked = matched = skipped = 0
    for vid, entry in VARIANTS.items():
        gene = entry["gene_symbol"]
        coords = GENE_COORDS.get(gene)
        if coords is None:
            logger.warning("%s: gene %s not in HR panel — skipping", vid, gene)
            skipped += 1
            continue
        checked += 1

        # The catalog doesn't ship chrom/pos directly for every entry (the
        # residue_positions list is protein-level). We can only check those
        # that also ship a chrom + pos from a VCF-style record; others get
        # flagged as "verify manually."
        chrom = entry.get("chrom")
        pos = entry.get("pos")
        ref = entry.get("ref")
        alt = entry.get("alt")
        if not all([chrom, pos, ref, alt]):
            logger.info("%s: no chrom/pos in catalog — verify manually", vid)
            continue

        key = (chrom, int(pos), ref, alt)
        if key in seen_sites:
            matched += 1
            logger.info("%s: ✓ matched %s:%d %s>%s", vid, chrom, pos, ref, alt)
        else:
            logger.warning(
                "%s: ✗ expected %s:%d %s>%s but gnomAD has no such record",
                vid, chrom, pos, ref, alt,
            )

    logger.info("\nsummary: checked=%d matched=%d skipped=%d",
                checked, matched, skipped)
    return 0 if checked == 0 or matched == checked else 1


if __name__ == "__main__":
    raise SystemExit(main())
