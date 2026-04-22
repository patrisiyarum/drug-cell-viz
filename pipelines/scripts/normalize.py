"""Normalize a VCF: split multi-allelic records, drop trivially malformed ones.

A "real" clinical pipeline would shell out to `bcftools norm -m-any -f REF`
here, which also left-aligns indels against a reference FASTA. We keep this
step in Python so the pipeline ships with zero system dependencies and runs
anywhere snakemake + cyvcf2 are available.

If you have bcftools + a reference, replace the body of this script with:
    subprocess.run(
        ["bcftools", "norm", "-m-any", "-f", reference, "-o", out, inp],
        check=True,
    )
"""

import logging
import sys
from pathlib import Path

from cyvcf2 import VCF, Writer

# Snakemake injects `snakemake` into the module globals when running this script.
snakemake = globals()["snakemake"]  # type: ignore[name-defined]
inp: str = snakemake.input.vcf
out: str = snakemake.output.vcf
log_path: str = snakemake.log[0]


def main() -> int:
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.info("normalize: %s -> %s", inp, out)

    vcf = VCF(inp)
    writer = Writer(out, vcf)

    total = 0
    written = 0
    split = 0

    for rec in vcf:
        total += 1

        # Skip records with no ALT (reference-only rows).
        if not rec.ALT:
            continue

        # Split multi-allelic records: emit one output record per ALT allele.
        # cyvcf2 doesn't expose a clean "clone with fewer ALTs" API, so we use
        # the textual representation and rewrite the ALT column.
        if len(rec.ALT) > 1:
            split += 1
            for alt in rec.ALT:
                line = str(rec).rstrip("\n").split("\t")
                line[4] = alt  # ALT column
                writer.write_record(_reparse_line(vcf, "\t".join(line)))
                written += 1
        else:
            writer.write_record(rec)
            written += 1

    writer.close()
    vcf.close()
    logging.info(
        "normalize done: %d input / %d output (%d split from multi-allelic)",
        total,
        written,
        split,
    )
    return 0


def _reparse_line(base_vcf: VCF, line: str):
    """Round-trip a textual VCF line through cyvcf2 for clean re-emission."""
    # cyvcf2.Variant is not directly constructible from text; the fastest
    # round-trip that preserves the header + sample columns is to write the
    # single line into a tempfile and re-open. For our tiny pipeline that's
    # fine. A production version would use pysam's VariantRecord.
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".vcf", delete=False) as tf:
        # Preserve the original header
        tf.write(str(base_vcf.raw_header))
        tf.write(line + "\n")
        tmp_path = tf.name
    single = VCF(tmp_path)
    rec = next(iter(single))
    return rec


if __name__ == "__main__":
    sys.exit(main())
