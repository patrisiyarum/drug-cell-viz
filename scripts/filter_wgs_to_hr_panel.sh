#!/usr/bin/env bash
#
# Pre-filter a personal whole-genome VCF down to just the HR-panel gene
# regions. Privacy-aware workflow: the output VCF contains only variants
# our pipeline actually scores. Everything outside the HR-panel stays
# on your machine.
#
# Works on:
#   - bgzipped + tabix-indexed VCFs (foo.vcf.gz + foo.vcf.gz.tbi)
#   - plain VCFs (will bgzip + index transiently)
#
# GRCh38 coordinates. If your WGS is on GRCh37, tell me and I'll add a lift.
#
# Usage:
#   bash scripts/filter_wgs_to_hr_panel.sh /path/to/your_wgs.vcf.gz \
#        fixtures/your_panel.vcf.gz

set -euo pipefail

src="${1:?usage: filter_wgs_to_hr_panel.sh <input.vcf[.gz]> <output.vcf.gz>}"
out="${2:?usage: filter_wgs_to_hr_panel.sh <input.vcf[.gz]> <output.vcf.gz>}"

for tool in bcftools tabix bgzip; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "missing required tool: $tool (install via 'brew install htslib bcftools')" >&2
        exit 2
    fi
done

# HR-panel gene regions (GRCh38). Wider than strict CDS so we catch deep
# intronic / splice variants the curated catalog already lists.
regions=$(cat <<'EOF'
chr17:43044295-43125483
chr17:58692573-58735461
chr17:35101353-35119221
chr17:61679193-61863563
chr13:32315474-32400266
chr16:23603160-23641310
chr11:108222832-108369102
chr22:28687820-28741585
chr2:214725646-214808175
chr1:226360251-226408154
chr22:42126499-42132544
chr1:97544001-97937000
EOF
)

mkdir -p "$(dirname "$out")"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Ensure the input is bgzipped + indexed; if not, make a transient copy.
input="$src"
case "$src" in
    *.vcf.gz) ;;
    *.vcf)
        echo "[prefilter] bgzipping + indexing $src" >&2
        cp "$src" "$tmp/in.vcf"
        bgzip -f "$tmp/in.vcf"
        tabix -p vcf "$tmp/in.vcf.gz"
        input="$tmp/in.vcf.gz"
        ;;
    *)
        echo "unexpected extension on $src — expect .vcf or .vcf.gz" >&2
        exit 3
        ;;
esac

if [ ! -f "${input}.tbi" ] && [ ! -f "${input}.csi" ]; then
    echo "[prefilter] indexing $input (missing .tbi/.csi)" >&2
    tabix -p vcf "$input"
fi

echo "[prefilter] filtering to HR-panel regions" >&2
bcftools view \
    --regions "$(echo "$regions" | paste -sd, -)" \
    --output-type z \
    --output "$out" \
    "$input"

tabix -p vcf "$out"

records=$(bcftools view -H "$out" | wc -l | tr -d ' ')
size=$(ls -lh "$out" | awk '{print $5}')
echo "[prefilter] wrote $out ($size, $records records)" >&2
echo ""
echo "Next: upload $out via /build's clinical-VCF dropzone,"
echo "or for maximum privacy run the whole app locally:"
echo "    docker compose up -d"
echo "    # then open http://localhost:3000/build"
