"""Genome-graph structural variant calling + HRD scar scoring.

Downstream of `fastq_to_vcf.smk`: once we have an aligned BAM, we realign
it onto a pangenome graph (HPRC or similar) to catch structural variants
that linear-reference alignment misses — critical for HRD scar detection
where rearrangements, LOH blocks, and allelic imbalance are the signal.

Two genome-graph backends:

  * `vg`:          Variation Graph Toolkit. `vg giraffe` re-aligns the
                   BAM onto a pangenome XG graph, `vg call` emits an SV
                   VCF. Mature, well-tested, widely cited.
  * `minigraph`:   Faster, graph-based with minimap2 heuristics. Good for
                   whole-genome scale screening.

The rule outputs a `scars.vcf.gz` (SV calls + genotypes) plus a
`hrd_features.json` file with the three integer counts the Python scar
scorer consumes: HRD-LOH, LST, NTAI. Those counts come from running
scarHRD-style aggregation on the SV VCF, done by `scripts/extract_hrd_features.py`.

Config additions (pipelines/config.yaml):

    pangenome_graph: /data/graphs/hprc-v1.1.gbz      # vg graph
    graph_backend:   vg                              # or "minigraph"
"""

from pathlib import Path

RESULTS_DIR = Path(config.get("results_dir", "results"))


rule genome_graph_sv_call:
    """Re-align BAM onto a pangenome graph + call structural variants.

    vg giraffe handles short-read alignment onto a gbz graph efficiently
    (~2× slower than BWA-MEM but catches SVs that collapse in linear
    alignment). The output is an SV VCF plus genotype-aware calls.
    """
    input:
        bam   = str(RESULTS_DIR / "{sample}" / "aligned.bam"),
        graph = config.get("pangenome_graph", "data/graphs/hprc-v1.1.gbz"),
    output:
        sv_vcf = str(RESULTS_DIR / "{sample}" / "scars.vcf.gz"),
    params:
        backend = config.get("graph_backend", "vg"),
        sample  = lambda w: w.sample,
    threads: config.get("threads_per_sample", 16)
    log:
        str(RESULTS_DIR / "{sample}" / "logs" / "genome_graph_sv.log"),
    shell:
        """
        set -euo pipefail
        if [ "{params.backend}" = "vg" ]; then
            bash {workflow.basedir}/scripts/run_vg_sv.sh \
                --bam      "{input.bam}" \
                --graph    "{input.graph}" \
                --vcf      "{output.sv_vcf}" \
                --threads  {threads} \
                --sample   "{params.sample}" \
                &> {log}
        else
            bash {workflow.basedir}/scripts/run_minigraph_sv.sh \
                --bam      "{input.bam}" \
                --graph    "{input.graph}" \
                --vcf      "{output.sv_vcf}" \
                --threads  {threads} \
                --sample   "{params.sample}" \
                &> {log}
        fi
        """


rule hrd_scar_features:
    """Aggregate the SV VCF into the three HRD scar counts.

    Implementation lives in `scripts/extract_hrd_features.py`; it reads
    the SV VCF with cyvcf2 and counts:
      - HRD-LOH regions (LOH > 15 Mb, not whole-chromosome)
      - LST transitions (copy-number/allelic breaks >= 10 Mb)
      - NTAI regions  (telomere-extending allelic imbalance)

    Output is a tiny JSON that the scoring service + API endpoint consume.
    """
    input:
        sv_vcf = str(RESULTS_DIR / "{sample}" / "scars.vcf.gz"),
    output:
        features = str(RESULTS_DIR / "{sample}" / "hrd_features.json"),
    log:
        str(RESULTS_DIR / "{sample}" / "logs" / "hrd_scar_features.log"),
    script:
        "../scripts/extract_hrd_features.py"


rule hrd_scar_score:
    """Run the HRDetect-style scorer on the feature counts."""
    input:
        features = str(RESULTS_DIR / "{sample}" / "hrd_features.json"),
    output:
        report = str(RESULTS_DIR / "{sample}" / "hrd_scars.json"),
    log:
        str(RESULTS_DIR / "{sample}" / "logs" / "hrd_scar_score.log"),
    script:
        "../scripts/score_hrd_scars.py"
