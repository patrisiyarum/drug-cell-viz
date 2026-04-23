#!/usr/bin/env bash
#
# Pull the HR-panel gene regions out of gnomAD v4.1 exomes into one small
# bgzipped VCF. Streams via tabix against gnomAD's public S3 bucket — no
# Google Cloud auth, no DACO. Total payload ~30 MB.

set -euo pipefail

out="${1:-data/gnomad/hr_panel.vcf.gz}"
mkdir -p "$(dirname "$out")"

# gnomAD v4.1 exomes per-chromosome sites VCFs on the public S3 mirror.
# (The GCS bucket works too but requires gsutil; S3 works with any HTTP client.)
base="https://gnomad-public-us-east-1.s3.amazonaws.com/release/4.1/vcf/exomes"

# HR-panel gene regions (GRCh38).
declare -A regions=(
    ["chr17"]="43044295-43125483 58692573-58735461 35101353-35119221 61679193-61863563"  # BRCA1, RAD51C, RAD51D, BRIP1
    ["chr13"]="32315474-32400266"    # BRCA2
    ["chr16"]="23603160-23641310"    # PALB2
    ["chr11"]="108222832-108369102"  # ATM
    ["chr22"]="28687820-28741585"    # CHEK2
    ["chr2"]="214725646-214808175"   # BARD1
    ["chr1"]="226360251-226408154"   # PARP1
)

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

first=1
for chrom in "${!regions[@]}"; do
    vcf="$base/gnomad.exomes.v4.1.sites.${chrom}.vcf.bgz"
    # tabix streams only the bytes it needs using the index.
    for region in ${regions[$chrom]}; do
        echo "[gnomad] $chrom:$region" >&2
        if [[ $first -eq 1 ]]; then
            tabix -h "$vcf" "${chrom}:${region}" > "$tmp/slice.vcf"
            first=0
        else
            tabix "$vcf" "${chrom}:${region}" >> "$tmp/slice.vcf"
        fi
    done
done

# Sort by chrom/pos (gnomAD is already sorted per chromosome, but we stitched
# slices from multiple chromosomes in dict iteration order) and bgzip + index.
bcftools sort "$tmp/slice.vcf" -Oz -o "$out"
tabix -p vcf "$out"

lines=$(bcftools view -H "$out" | wc -l | tr -d ' ')
size=$(ls -lh "$out" | awk '{print $5}')
echo "[gnomad] wrote $out ($size, $lines records across HR panel)" >&2
