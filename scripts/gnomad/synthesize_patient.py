"""Synthesize a realistic per-patient VCF by sampling from gnomAD allele
frequencies.

gnomAD publishes per-population AF; we draw a genotype at each variant in the
HR panel by calling rbinom(2, AF) — giving 0/1/2 risk alleles (hom-ref,
het, hom-alt) with realistic population frequencies. The resulting VCF has
the same format the /build VCF uploader already consumes.

Most generated "patients" will have no clinically-meaningful variants
(because HR-panel pathogenic variants are rare and most sampled
heterozygotes are benign common variants). That's the point — a pipeline
that hallucinates findings on a random person is a buggy pipeline.

For a fixed pathogenic test case, pass `--inject <variant_id>` to splice a
specific catalog variant into the output.
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

logger = logging.getLogger("synthesize_patient")

# gnomAD v4.1 population AF INFO-field suffixes.
POPULATIONS = {
    "afr": "AF_afr",         # African/African American
    "ami": "AF_ami",         # Amish
    "amr": "AF_amr",         # Latino/Admixed American
    "asj": "AF_asj",         # Ashkenazi Jewish
    "eas": "AF_eas",         # East Asian
    "fin": "AF_fin",         # Finnish
    "nfe": "AF_nfe",         # Non-Finnish European
    "sas": "AF_sas",         # South Asian
    "mid": "AF_mid",         # Middle Eastern
    "global": "AF",          # pooled AF
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gnomad", required=True, type=Path,
                   help="HR-panel gnomAD VCF (from extract_hr_panel.sh)")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument(
        "--population", default="nfe", choices=list(POPULATIONS),
        help="gnomAD population whose AFs drive the genotype draw",
    )
    p.add_argument("--sample-name", default="synthetic_patient")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument(
        "--max-af", type=float, default=0.5,
        help="Skip very common variants (AF > max-af) so we're not drowning in "
             "noise from fixed ref alleles. 0.5 keeps heterozygous-leaning common "
             "variants; 0.01 would give a rare-only set.",
    )
    p.add_argument(
        "--inject", nargs="*", default=[],
        help="Catalog variant IDs to force into the output regardless of AF draw, "
             "e.g. --inject BRCA1_C61G",
    )
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        from cyvcf2 import VCF
    except ImportError:
        logger.error("cyvcf2 required — run `uv sync --extra pipeline --package api`")
        return 2

    rng = random.Random(args.seed)
    af_field = POPULATIONS[args.population]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    vcf = VCF(str(args.gnomad))

    header_lines = vcf.raw_header.splitlines()
    # Drop gnomAD's sample header if any (sites-only VCFs don't have samples,
    # but guard against future changes) and write our own.
    header_lines = [ln for ln in header_lines if not ln.startswith("#CHROM")]
    header_lines.append(
        "##INFO=<ID=SYNTH,Number=0,Type=Flag,Description=\"Synthesised from gnomAD AF\">"
    )
    header_lines.append(
        f"##FORMAT=<ID=GT,Number=1,Type=String,Description=\"Genotype\">"
    )
    header_lines.append(f"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t{args.sample_name}")

    n_total = 0
    n_het = 0
    n_hom = 0
    with args.out.open("w") as f:
        f.write("\n".join(header_lines) + "\n")
        for rec in vcf:
            af = rec.INFO.get(af_field)
            if af is None or af == ".":
                continue
            try:
                af = float(af)
            except (TypeError, ValueError):
                continue
            if af <= 0 or af > args.max_af:
                continue
            # Diploid draw: binomial(2, af) → 0/1/2 alt alleles.
            alts = sum(1 for _ in range(2) if rng.random() < af)
            if alts == 0:
                continue
            gt = "0/1" if alts == 1 else "1/1"
            alt = rec.ALT[0] if rec.ALT else ""
            if not alt:
                continue
            info = f"SYNTH;AF_{args.population}={af:.5f}"
            f.write(
                f"{rec.CHROM}\t{rec.POS}\t.\t{rec.REF}\t{alt}\t.\tPASS\t{info}\tGT\t{gt}\n"
            )
            n_total += 1
            if alts == 1:
                n_het += 1
            else:
                n_hom += 1

    # Inject any forced catalog variants.
    if args.inject:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/api/src"))
        from api.services.bc_catalog import VARIANTS

        with args.out.open("a") as f:
            for vid in args.inject:
                entry = VARIANTS.get(vid)
                if entry is None:
                    logger.warning("inject: unknown catalog variant %s", vid)
                    continue
                chrom = entry.get("chrom")
                pos = entry.get("pos")
                ref = entry.get("ref")
                alt = entry.get("alt")
                if not all([chrom, pos, ref, alt]):
                    logger.warning(
                        "inject: %s has no chrom/pos in catalog; skipping", vid,
                    )
                    continue
                f.write(
                    f"{chrom}\t{pos}\t{vid}\t{ref}\t{alt}\t.\tPASS\tSYNTH;INJECTED\tGT\t0/1\n"
                )
                logger.info("injected %s at %s:%d %s>%s", vid, chrom, pos, ref, alt)
                n_het += 1
                n_total += 1

    logger.info(
        "wrote %s: %d variants (%d het, %d hom)",
        args.out, n_total, n_het, n_hom,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
