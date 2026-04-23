#!/usr/bin/env bash
#
# CPU fallback: BWA-MEM 2 + samtools + GATK4 HaplotypeCaller.
#
# Same input/output contract as `run_parabricks.sh` so the Snakemake rule
# can route between GPU and CPU backends by flipping one config flag.
# Runtime on a 32-core box for 30× WGS: ~9 hours total.
#
# Expects the following on PATH (any package manager works):
#   bwa-mem2, samtools, gatk (or gatk4)
# Expects the reference to be pre-indexed:
#   bwa-mem2 index <ref.fa>
#   samtools faidx <ref.fa>
#   gatk CreateSequenceDictionary -R <ref.fa>

set -euo pipefail

r1=""
r2=""
reference=""
bam=""
vcf=""
rg=""
threads="16"
sample=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --r1)        r1="$2";        shift 2 ;;
        --r2)        r2="$2";        shift 2 ;;
        --reference) reference="$2"; shift 2 ;;
        --bam)       bam="$2";       shift 2 ;;
        --vcf)       vcf="$2";       shift 2 ;;
        --rg)        rg="$2";        shift 2 ;;
        --threads)   threads="$2";   shift 2 ;;
        --sample)    sample="$2";    shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

[[ -z "$r1"        ]] && { echo "missing --r1";        exit 2; }
[[ -z "$r2"        ]] && { echo "missing --r2";        exit 2; }
[[ -z "$reference" ]] && { echo "missing --reference"; exit 2; }
[[ -z "$bam"       ]] && { echo "missing --bam";       exit 2; }
[[ -z "$vcf"       ]] && { echo "missing --vcf";       exit 2; }

for tool in bwa-mem2 samtools gatk; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "missing required tool on PATH: $tool" >&2
        exit 3
    fi
done

mkdir -p "$(dirname "$bam")" "$(dirname "$vcf")"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "[bwa-gatk] sample=$sample threads=$threads"

# --- align ---------------------------------------------------------------
# `-R` expects a tab-separated read-group header; the Snakemake rule passes
# the RG string already escaped with \t sequences.
bwa-mem2 mem -t "$threads" -R "$(printf '@RG\t%s' "$rg")" "$reference" "$r1" "$r2" \
    | samtools sort -@ "$threads" -o "$tmp/sorted.bam" -
samtools index -@ "$threads" "$tmp/sorted.bam"

# --- mark duplicates -----------------------------------------------------
gatk MarkDuplicates \
    -I "$tmp/sorted.bam" \
    -O "$bam" \
    -M "$tmp/dup_metrics.txt"
samtools index -@ "$threads" "$bam"

# --- call variants -------------------------------------------------------
# -ERC GVCF gives us a gVCF we could later join; we collapse to a regular
# VCF for downstream consumption so output is a drop-in match for the
# Parabricks branch.
gatk HaplotypeCaller \
    -R "$reference" \
    -I "$bam" \
    -O "$tmp/raw.vcf.gz" \
    --native-pair-hmm-threads "$threads"

cp "$tmp/raw.vcf.gz" "$vcf"

echo "[bwa-gatk] done — bam=$bam  vcf=$vcf"
