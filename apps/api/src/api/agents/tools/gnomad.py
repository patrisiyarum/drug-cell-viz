"""gnomAD lookup via their public GraphQL API.

gnomAD aggregates exome + genome sequencing data from ~800,000 individuals
across the major sequencing consortia. For variant interpretation it
answers one specific, important question: how often does this variant
appear in the general population?

A pathogenic-looking variant that turns up in 5% of healthy people is
almost certainly NOT pathogenic — common variants don't cause severe
disease (at least not as a single-gene mendelian effect). Conversely,
a variant absent from gnomAD in 800,000 people is consistent with rare
pathogenic — though absence is not proof.

The GraphQL endpoint is free, public, no auth required.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GNOMAD_GRAPHQL = "https://gnomad.broadinstitute.org/api"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)

# Frequency above which we'd consider a variant "common" — reasonably
# inconsistent with high-penetrance Mendelian pathogenicity. 0.5% is the
# conservative ACMG cutoff; we surface the actual freq alongside so
# clinicians can make their own call.
COMMON_AF_THRESHOLD = 0.005


async def allele_frequency(gene: str, hgvs_protein: str) -> dict[str, Any]:
    """Look up a variant's population allele frequency in gnomAD v4.

    gnomAD's GraphQL doesn't search by HGVS-protein directly — it indexes
    by HGVSc (cDNA) or chrom-pos-ref-alt. The pragmatic approach: search
    the gene's variant list and filter for matches on the protein change.

    Args:
        gene: HGNC gene symbol
        hgvs_protein: HGVS protein notation (e.g. "p.Cys61Gly")

    Returns:
        Dict with status + allele_frequency + ac (allele count) + an / af
        per population, and a derived "is_rare" flag.
    """
    # Normalize protein notation. gnomAD stores HGVSp like "p.Cys61Gly".
    needle = hgvs_protein if hgvs_protein.startswith("p.") else f"p.{hgvs_protein}"

    query = """
    query GeneVariants($gene: String!, $dataset: DatasetId!) {
      gene(gene_symbol: $gene, reference_genome: GRCh38) {
        variants(dataset: $dataset) {
          variant_id
          hgvsp
          consequence
          exome { ac an af populations { id af ac an } }
          genome { ac an af populations { id af ac an } }
        }
      }
    }
    """

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.post(
                GNOMAD_GRAPHQL,
                json={
                    "query": query,
                    "variables": {"gene": gene, "dataset": "gnomad_r4"},
                },
            )
            r.raise_for_status()
            payload = r.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("gnomAD lookup failed for %s %s: %s", gene, hgvs_protein, exc)
            return {
                "status": "error",
                "reason": f"gnomAD GraphQL call failed: {exc}",
                "gene": gene,
                "hgvs_protein": hgvs_protein,
            }

    gene_data = (payload.get("data") or {}).get("gene")
    if not gene_data:
        return {
            "status": "not_found",
            "reason": f"gnomAD has no variant index for gene {gene}.",
            "gene": gene,
            "hgvs_protein": hgvs_protein,
        }

    matches = [
        v for v in gene_data.get("variants", []) or []
        if v.get("hgvsp") and needle.lower() in v["hgvsp"].lower()
    ]
    if not matches:
        return {
            "status": "absent",
            "reason": (
                f"Variant {gene} {hgvs_protein} is absent from gnomAD v4 "
                "(800,000 sequenced individuals). Absence is consistent "
                "with rare/pathogenic but is not proof."
            ),
            "gene": gene,
            "hgvs_protein": hgvs_protein,
            "is_rare": True,
        }

    # Pick the highest-frequency match (multiple HGVSp annotations from
    # different transcripts can index the same protein change; take the
    # most sensitive).
    matches.sort(
        key=lambda v: max(
            (v.get("exome") or {}).get("af") or 0.0,
            (v.get("genome") or {}).get("af") or 0.0,
        ),
        reverse=True,
    )
    best = matches[0]
    exome = best.get("exome") or {}
    genome = best.get("genome") or {}
    af = max((exome.get("af") or 0.0), (genome.get("af") or 0.0))

    return {
        "status": "ok",
        "variant_id": best.get("variant_id"),
        "consequence": best.get("consequence"),
        "allele_frequency": af,
        "exome_ac": exome.get("ac"),
        "exome_an": exome.get("an"),
        "genome_ac": genome.get("ac"),
        "genome_an": genome.get("an"),
        "is_rare": af < COMMON_AF_THRESHOLD,
        "url": f"https://gnomad.broadinstitute.org/variant/{best.get('variant_id')}",
        "gene": gene,
        "hgvs_protein": hgvs_protein,
    }
