"""FASTQ → BAM → VCF, GPU-accelerated via NVIDIA Clara Parabricks.

This is the upstream half of the pipeline: take raw paired-end sequencing
reads, align them to GRCh38, and call germline variants. The output VCF
is the same format the rest of this project already consumes, so dropping
this rule in front of the existing normalize → filter_catalog → classify
chain lets a patient hand us a FASTQ and get a full analysis back.

Two execution backends:

  * `parabricks` (default when available): NVIDIA Clara Parabricks running
    on an A100/H100 GPU. `fq2bam` replaces BWA-MEM + samtools sort in
    ~20 minutes on a 30× whole-genome sample; `haplotypecaller` replaces
    GATK HaplotypeCaller in ~25 minutes. Expects a Parabricks license and
    a container runtime (docker or singularity).

  * `bwa_gatk` (fallback): the traditional CPU pipeline using BWA-MEM 2
    + GATK4 HaplotypeCaller. 10-20× slower but runs anywhere; the rule
    shells out to `scripts/run_bwa_gatk.sh`.

Config (pipelines/config.yaml):

    fastq_samples:
      patient_42:
        fastq_r1: data/raw/patient_42_R1.fastq.gz
        fastq_r2: data/raw/patient_42_R2.fastq.gz
        read_group: "ID:42\\tSM:42\\tLB:lib1\\tPL:ILLUMINA"

    reference_fa: /data/genome/GRCh38.fa
    fastq_backend: parabricks   # or "bwa_gatk"
    parabricks_image: nvcr.io/nvidia/clara/clara-parabricks:4.3.1-1
    threads_per_sample: 16

Once this rule emits a VCF per FASTQ sample, the rest of the pipeline
(normalize, filter_catalog, classify) is identical.
"""

from pathlib import Path

FASTQ_SAMPLES = list(config.get("fastq_samples", {}).keys())


rule fastq_to_vcf:
    """Align FASTQ + call germline variants.

    Routes to Parabricks on GPU by default, falls back to BWA-MEM2 + GATK4
    when fastq_backend="bwa_gatk" (or when no GPU is available at runtime).
    Both wrappers emit a bgzipped VCF at the same path so downstream rules
    don't care which backend ran.
    """
    input:
        r1 = lambda w: config["fastq_samples"][w.sample]["fastq_r1"],
        r2 = lambda w: config["fastq_samples"][w.sample]["fastq_r2"],
        reference = config.get("reference_fa", "data/genome/GRCh38.fa"),
    output:
        bam = str(Path(config.get("results_dir", "results")) / "{sample}" / "aligned.bam"),
        vcf = str(Path(config.get("results_dir", "results")) / "{sample}" / "called.vcf.gz"),
    params:
        backend     = config.get("fastq_backend", "parabricks"),
        image       = config.get("parabricks_image", "nvcr.io/nvidia/clara/clara-parabricks:4.3.1-1"),
        read_group  = lambda w: config["fastq_samples"][w.sample].get(
            "read_group", f"ID:{w.sample}\\tSM:{w.sample}\\tLB:lib1\\tPL:ILLUMINA",
        ),
        sample      = lambda w: w.sample,
    threads: config.get("threads_per_sample", 16)
    log:
        str(Path(config.get("results_dir", "results")) / "{sample}" / "logs" / "fastq_to_vcf.log"),
    shell:
        """
        set -euo pipefail
        if [ "{params.backend}" = "parabricks" ]; then
            bash {workflow.basedir}/scripts/run_parabricks.sh \
                --image     "{params.image}" \
                --r1        "{input.r1}" \
                --r2        "{input.r2}" \
                --reference "{input.reference}" \
                --bam       "{output.bam}" \
                --vcf       "{output.vcf}" \
                --rg        "{params.read_group}" \
                --threads   {threads} \
                --sample    "{params.sample}" \
                &> {log}
        else
            bash {workflow.basedir}/scripts/run_bwa_gatk.sh \
                --r1        "{input.r1}" \
                --r2        "{input.r2}" \
                --reference "{input.reference}" \
                --bam       "{output.bam}" \
                --vcf       "{output.vcf}" \
                --rg        "{params.read_group}" \
                --threads   {threads} \
                --sample    "{params.sample}" \
                &> {log}
        fi
        """
