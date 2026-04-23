"""Aggregate a structural-variant VCF into the three HRD scar counts.

Inputs:
    SV VCF produced by `vg call` or `minigraph --call` — each record is a
    structural-variant bubble with genotype, sample, and span annotations.

Outputs:
    A minimal JSON: {"loh": <int>, "lst": <int>, "ntai": <int>, "total": <int>}

Aggregation rules (simplified scarHRD-style):
    * HRD-LOH: deletions / copy-neutral LOH regions >= 15 Mb that do NOT
               span an entire chromosome. These are the classical Myriad
               `LOH` features.
    * LST:     Breakpoints where chromosome copy-number or allelic state
               changes, with both flanking regions >= 10 Mb.
    * NTAI:    Allele-imbalanced regions whose outer boundary coincides
               with a telomere (first or last Mb of a chromosome arm),
               not extending through the whole chromosome.

This is a *demonstration* implementation. A clinical-grade scar caller
needs BAF tracks from paired tumor/normal coverage plus chromosome-arm
boundaries from a cytoband BED; we approximate that using the SV VCF's
END coordinates and SVTYPE. Swap this script for a production scarHRD /
HRDetect runner when available.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

# snakemake-provided: `snakemake.input`, `snakemake.output`, `snakemake.log`
sm = globals().get("snakemake")
logger = logging.getLogger("hrd_features")


# Rough per-chromosome lengths in base pairs (GRCh38, sexchr excluded).
# Used to classify "whole-chromosome" vs "partial" LOH regions.
CHROM_LENGTHS_BP: dict[str, int] = {
    "chr1": 248_956_422, "chr2": 242_193_529, "chr3": 198_295_559,
    "chr4": 190_214_555, "chr5": 181_538_259, "chr6": 170_805_979,
    "chr7": 159_345_973, "chr8": 145_138_636, "chr9": 138_394_717,
    "chr10": 133_797_422, "chr11": 135_086_622, "chr12": 133_275_309,
    "chr13": 114_364_328, "chr14": 107_043_718, "chr15": 101_991_189,
    "chr16": 90_338_345, "chr17": 83_257_441, "chr18": 80_373_285,
    "chr19": 58_617_616, "chr20": 64_444_167, "chr21": 46_709_983,
    "chr22": 50_818_468, "chrX": 156_040_895, "chrY": 57_227_415,
}

LOH_MIN_SIZE_BP = 15_000_000   # 15 Mb — Myriad myChoice cutoff
LST_MIN_FLANK_BP = 10_000_000  # 10 Mb either side of a break
NTAI_TELOMERE_WINDOW_BP = 3_000_000  # within 3 Mb of a chromosome end


def _aggregate(vcf_path: Path) -> dict[str, int]:
    """Walk the SV VCF once, emit the three counts. Graceful on empty/missing input."""
    try:
        from cyvcf2 import VCF
    except ImportError as exc:  # pragma: no cover — deps are always present in this env
        raise RuntimeError("cyvcf2 is required for HRD feature extraction") from exc

    loh = 0
    lst = 0
    ntai = 0

    if not vcf_path.exists() or vcf_path.stat().st_size == 0:
        logger.warning("SV VCF missing or empty at %s — emitting zero counts", vcf_path)
        return {"loh": 0, "lst": 0, "ntai": 0, "total": 0}

    for rec in VCF(str(vcf_path)):
        chrom = rec.CHROM if rec.CHROM.startswith("chr") else f"chr{rec.CHROM}"
        start = int(rec.POS)
        end = int(rec.INFO.get("END") or start)
        svtype = (rec.INFO.get("SVTYPE") or "").upper()
        chrom_len = CHROM_LENGTHS_BP.get(chrom)
        span = end - start

        if chrom_len is None:
            continue

        is_whole_chrom = span >= chrom_len * 0.9
        near_telomere = start < NTAI_TELOMERE_WINDOW_BP or (
            chrom_len - end < NTAI_TELOMERE_WINDOW_BP
        )

        # HRD-LOH: large partial deletions / CN-LOH tracts
        if svtype in {"DEL", "CNV", "LOH"} and span >= LOH_MIN_SIZE_BP and not is_whole_chrom:
            loh += 1

        # LST: any structural-variant breakpoint with both flanks >= 10 Mb
        if svtype in {"DEL", "DUP", "INV", "CNV", "BND"}:
            left_flank = start
            right_flank = chrom_len - end
            if left_flank >= LST_MIN_FLANK_BP and right_flank >= LST_MIN_FLANK_BP:
                lst += 1

        # NTAI: telomere-extending allelic imbalance, not whole-chromosome
        if near_telomere and svtype in {"DEL", "DUP", "CNV", "LOH"} and not is_whole_chrom:
            ntai += 1

    total = loh + lst + ntai
    return {"loh": loh, "lst": lst, "ntai": ntai, "total": total}


def main() -> None:
    if sm is None:
        raise SystemExit("this script is meant to run via Snakemake")
    logging.basicConfig(
        filename=str(sm.log[0]) if sm.log else None,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    vcf_path = Path(sm.input.sv_vcf)
    out_path = Path(sm.output.features)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    counts = _aggregate(vcf_path)
    out_path.write_text(json.dumps(counts, indent=2))
    logger.info("features: %s", counts)


if __name__ == "__main__":
    main()
