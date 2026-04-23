#!/usr/bin/env bash
#
# vg (Variation Graph Toolkit) wrapper: BAM → pangenome re-alignment → SV VCF.
#
# Uses vg giraffe for fast short-read alignment onto a gbz pangenome graph,
# then vg call for genotype-aware structural-variant calling. vg catches
# SVs (inversions, large deletions, translocations) that collapse in linear
# GRCh38 alignment — critical for HRD scar detection where rearrangements
# are the clinical signal.
#
# Expects on PATH:  vg, samtools
# Docs: https://github.com/vgteam/vg

set -euo pipefail

bam=""
graph=""
vcf=""
threads="16"
sample=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bam)     bam="$2";     shift 2 ;;
        --graph)   graph="$2";   shift 2 ;;
        --vcf)     vcf="$2";     shift 2 ;;
        --threads) threads="$2"; shift 2 ;;
        --sample)  sample="$2";  shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

[[ -z "$bam"     ]] && { echo "missing --bam";     exit 2; }
[[ -z "$graph"   ]] && { echo "missing --graph";   exit 2; }
[[ -z "$vcf"     ]] && { echo "missing --vcf";     exit 2; }
[[ -z "$sample"  ]] && { echo "missing --sample";  exit 2; }

for tool in vg samtools; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "missing required tool on PATH: $tool" >&2
        exit 3
    fi
done

mkdir -p "$(dirname "$vcf")"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "[vg] sample=$sample graph=$graph threads=$threads"

# --- BAM → FASTQ → vg giraffe --------------------------------------------
# Giraffe takes paired FASTQ. If the BAM is coordinate-sorted we convert
# back to a pair of FASTQs via samtools. For a pure SV call path, vg also
# accepts BAM directly via `vg inject`, but starting from FASTQ is simpler
# and matches upstream Parabricks output.
samtools collate -@ "$threads" -O -u "$bam" "$tmp/collate" \
    | samtools fastq -@ "$threads" -1 "$tmp/r1.fq.gz" -2 "$tmp/r2.fq.gz" -

# --- giraffe: align onto graph -------------------------------------------
# Emit a .gam (graph alignment) that vg call consumes.
vg giraffe --progress \
    -Z "$graph" \
    -f "$tmp/r1.fq.gz" \
    -f "$tmp/r2.fq.gz" \
    -t "$threads" \
    -o gam > "$tmp/aligned.gam"

# --- pack coverage + vg call → SV VCF -----------------------------------
vg pack -x "$graph" -g "$tmp/aligned.gam" -t "$threads" -o "$tmp/aligned.pack"
vg call "$graph" -k "$tmp/aligned.pack" -t "$threads" -s "$sample" \
    --all-snarls \
    > "$tmp/calls.vcf"
bgzip -@ "$threads" "$tmp/calls.vcf"
tabix -p vcf "$tmp/calls.vcf.gz"

cp "$tmp/calls.vcf.gz" "$vcf"
cp "$tmp/calls.vcf.gz.tbi" "$vcf.tbi"

echo "[vg] done — vcf=$vcf"
