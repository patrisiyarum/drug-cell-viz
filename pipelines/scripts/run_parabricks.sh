#!/usr/bin/env bash
#
# NVIDIA Clara Parabricks wrapper: FASTQ → BAM → VCF on GPU.
#
# Requires a Parabricks licence and either docker or singularity with
# CUDA-enabled GPU access. Pulls the Parabricks container from NGC and
# runs `pbrun fq2bam` followed by `pbrun haplotypecaller`.
#
# Runtime on an A100 for a 30× WGS sample: ~45 minutes total (alignment
# + variant calling). Same workload on 32-CPU bwa-mem2 + GATK: ~9 hours.
#
# Parabricks docs:
#   https://docs.nvidia.com/clara/parabricks/latest/gettingstarted.html

set -euo pipefail

# --- arg parsing ---------------------------------------------------------
image=""
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
        --image)     image="$2";     shift 2 ;;
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

[[ -z "$image"     ]] && { echo "missing --image";     exit 2; }
[[ -z "$r1"        ]] && { echo "missing --r1";        exit 2; }
[[ -z "$r2"        ]] && { echo "missing --r2";        exit 2; }
[[ -z "$reference" ]] && { echo "missing --reference"; exit 2; }
[[ -z "$bam"       ]] && { echo "missing --bam";       exit 2; }
[[ -z "$vcf"       ]] && { echo "missing --vcf";       exit 2; }
[[ -z "$sample"    ]] && { echo "missing --sample";    exit 2; }

# --- host paths → container mounts ---------------------------------------
# Parabricks needs to see the reference, the FASTQs, and a writable output
# area. We bind the directories of each input separately so the container
# sees them at /inputs/refs, /inputs/reads, /outputs.
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$(dirname "$bam")" "$(dirname "$vcf")"

ref_dir=$(cd "$(dirname "$reference")" && pwd)
ref_name=$(basename "$reference")
reads_dir=$(cd "$(dirname "$r1")" && pwd)
r1_name=$(basename "$r1")
r2_name=$(basename "$r2")
bam_dir=$(cd "$(dirname "$bam")" && pwd)
bam_name=$(basename "$bam")
vcf_dir=$(cd "$(dirname "$vcf")" && pwd)
vcf_name=$(basename "$vcf")

# Prefer docker, fall back to singularity. Both need --gpus / --nv for CUDA.
if command -v docker >/dev/null 2>&1; then
    runtime="docker"
elif command -v singularity >/dev/null 2>&1; then
    runtime="singularity"
else
    echo "neither docker nor singularity found on PATH — can't run Parabricks" >&2
    exit 3
fi

echo "[parabricks] runtime=$runtime image=$image sample=$sample threads=$threads"

# --- fq2bam: BWA-MEM + mark duplicates, GPU-accelerated -----------------
if [[ "$runtime" == "docker" ]]; then
    docker run --rm --gpus all \
        -v "$ref_dir":/inputs/refs:ro \
        -v "$reads_dir":/inputs/reads:ro \
        -v "$bam_dir":/outputs/bam \
        "$image" pbrun fq2bam \
            --ref "/inputs/refs/$ref_name" \
            --in-fq "/inputs/reads/$r1_name" "/inputs/reads/$r2_name" "$rg" \
            --out-bam "/outputs/bam/$bam_name" \
            --num-cpu-threads-per-stage "$threads"
else
    singularity exec --nv \
        -B "$ref_dir":/inputs/refs \
        -B "$reads_dir":/inputs/reads \
        -B "$bam_dir":/outputs/bam \
        "docker://$image" pbrun fq2bam \
            --ref "/inputs/refs/$ref_name" \
            --in-fq "/inputs/reads/$r1_name" "/inputs/reads/$r2_name" "$rg" \
            --out-bam "/outputs/bam/$bam_name" \
            --num-cpu-threads-per-stage "$threads"
fi

# --- haplotypecaller: germline variant calling, GPU-accelerated ---------
if [[ "$runtime" == "docker" ]]; then
    docker run --rm --gpus all \
        -v "$ref_dir":/inputs/refs:ro \
        -v "$bam_dir":/inputs/bam:ro \
        -v "$vcf_dir":/outputs/vcf \
        "$image" pbrun haplotypecaller \
            --ref "/inputs/refs/$ref_name" \
            --in-bam "/inputs/bam/$bam_name" \
            --out-variants "/outputs/vcf/$vcf_name" \
            --num-cpu-threads-per-stage "$threads"
else
    singularity exec --nv \
        -B "$ref_dir":/inputs/refs \
        -B "$bam_dir":/inputs/bam \
        -B "$vcf_dir":/outputs/vcf \
        "docker://$image" pbrun haplotypecaller \
            --ref "/inputs/refs/$ref_name" \
            --in-bam "/inputs/bam/$bam_name" \
            --out-variants "/outputs/vcf/$vcf_name" \
            --num-cpu-threads-per-stage "$threads"
fi

echo "[parabricks] done — bam=$bam  vcf=$vcf"
