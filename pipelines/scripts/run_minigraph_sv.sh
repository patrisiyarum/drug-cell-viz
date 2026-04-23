#!/usr/bin/env bash
#
# minigraph wrapper: BAM → pangenome re-alignment → SV VCF.
#
# Faster alternative to vg when you care more about throughput than about
# per-allele precision. minigraph uses minimap2-style heuristics so it
# handles whole-genome runs in hours rather than a day.
#
# Expects on PATH:  minigraph, samtools, bgzip, tabix
# Docs: https://github.com/lh3/minigraph

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

for tool in minigraph samtools bgzip tabix; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "missing required tool on PATH: $tool" >&2
        exit 3
    fi
done

mkdir -p "$(dirname "$vcf")"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "[minigraph] sample=$sample graph=$graph threads=$threads"

samtools collate -@ "$threads" -O -u "$bam" "$tmp/collate" \
    | samtools fastq -@ "$threads" -1 "$tmp/r1.fq.gz" -2 "$tmp/r2.fq.gz" -

# --- minigraph --call: emits GAF with bubble-level SV records -----------
minigraph -t "$threads" -cx sr "$graph" "$tmp/r1.fq.gz" "$tmp/r2.fq.gz" \
    > "$tmp/aligned.gaf"

# --- minigraph -C bubble summary → VCF (naive conversion) ---------------
# minigraph's --call emits GAF; the canonical bubble-to-VCF conversion
# is done by `minigraph --call` with a per-contig reference, or in the
# MC pangenome workflow via `vcfbub`. For a standalone call we use the
# minigraph-bundled helper script.
minigraph -cx asm --call \
    -t "$threads" \
    "$graph" \
    "$tmp/aligned.gaf" \
    > "$tmp/calls.vcf"

# Inject the sample name header line so downstream tools can identify the run.
sed -i.bak "s/SAMPLE/${sample}/" "$tmp/calls.vcf"
rm -f "$tmp/calls.vcf.bak"

bgzip -@ "$threads" "$tmp/calls.vcf"
tabix -p vcf "$tmp/calls.vcf.gz"

cp "$tmp/calls.vcf.gz" "$vcf"
cp "$tmp/calls.vcf.gz.tbi" "$vcf.tbi"

echo "[minigraph] done — vcf=$vcf"
