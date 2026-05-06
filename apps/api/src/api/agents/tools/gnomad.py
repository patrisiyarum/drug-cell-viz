"""gnomAD lookup via the public GraphQL API.

Two-stage query path:

    1. Translate the variant from HGVS protein notation (e.g.
       'BRCA1 p.Cys61Gly') to a gnomAD variant_id (chrom-pos-ref-alt
       on the forward strand of GRCh38). For demo variants we keep an
       in-process lookup table — translation is otherwise a multi-step
       process (Ensembl variant_recoder, transcript-aware) and the
       extra hop is brittle for a real-time agent.

    2. Hit gnomAD's `variant(variantId, dataset: gnomad_r4)` query,
       which returns the per-population AC/AN/AF + transcript
       consequences in one call. This is the API path gnomAD itself
       expects you to use for known-variant lookups; it's much more
       reliable than pulling every variant for a gene and filtering.

The earlier `gene.variants` approach pulled megabytes of data for
large genes like BRCA1 and routinely timed out. This rewrite is the
right shape for the use case.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GNOMAD_GRAPHQL = "https://gnomad.broadinstitute.org/api"
TIMEOUT = httpx.Timeout(30.0, connect=5.0)

# Frequency above which a variant is "common" — inconsistent with
# high-penetrance Mendelian pathogenicity. 0.5% is the conservative
# ACMG cutoff; we surface the actual frequency alongside so a
# clinician can make their own call.
COMMON_AF_THRESHOLD = 0.005

# Curated HGVS-protein → gnomAD variant_id table for the demo patients
# and a few well-studied BRCA1/2 founders. Keys are normalized to
# "GENE:p.XXX" — the lookup function strips whitespace and prepends
# "p." if missing. variant_id format is gnomAD's standard
# chrom-pos-ref-alt on the GRCh38 forward strand.
#
# To extend: ClinVar -> Variation Viewer shows the GRCh38 coordinate.
# Translate by hand once, paste here, never look back.
_VARIANT_ID_BY_HGVS: dict[str, str] = {
    # BRCA1 p.Cys61Gly — c.181T>G, in the RING domain. Maya's variant.
    # BRCA1 is on the minus strand, so the transcript T>G is forward A>C.
    "BRCA1:p.Cys61Gly": "17-43106487-A-C",
    # BRCA2 founder variants — useful for downstream demo patients.
    # c.5946delT (legacy 6174delT), one of the AJ founder variants.
    # Priya's variant in the demo seed.
    "BRCA2:c.5946delT": "13-32340301-AT-A",
}


async def allele_frequency(gene: str, hgvs_protein: str) -> dict[str, Any]:
    """Look up a variant's population allele frequency in gnomAD v4.

    Args:
        gene: HGNC gene symbol
        hgvs_protein: HGVS protein notation (or cDNA notation for
            non-protein-coding changes like the BRCA2 founder deletion)

    Returns:
        Dict with status + allele_frequency + AC/AN per dataset
        (exome, genome) and a derived "is_rare" flag.
    """
    key = _normalize_key(gene, hgvs_protein)
    variant_id = _VARIANT_ID_BY_HGVS.get(key)
    if variant_id is None:
        return {
            "status": "not_found",
            "reason": (
                f"No gnomAD variant_id mapping for {gene} {hgvs_protein}. "
                "The agent looks up variants by GRCh38 coordinate; "
                "extending coverage means adding entries to the "
                "_VARIANT_ID_BY_HGVS table."
            ),
            "gene": gene,
            "hgvs_protein": hgvs_protein,
        }

    query = """
    query VariantById($variantId: String!, $dataset: DatasetId!) {
      variant(variantId: $variantId, dataset: $dataset) {
        variant_id
        rsids
        exome { ac an af }
        genome { ac an af }
        transcript_consequences {
          gene_symbol
          hgvsp
          consequence_terms
          major_consequence
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
                    "variables": {
                        "variantId": variant_id,
                        "dataset": "gnomad_r4",
                    },
                },
            )
            r.raise_for_status()
            payload = r.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "gnomAD lookup failed for %s %s (%s): %s",
                gene, hgvs_protein, variant_id, exc,
            )
            return {
                "status": "error",
                "reason": f"gnomAD GraphQL call failed: {exc}",
                "gene": gene,
                "hgvs_protein": hgvs_protein,
                "variant_id": variant_id,
            }

    if payload.get("errors"):
        return {
            "status": "error",
            "reason": "gnomAD GraphQL errors: "
                     + "; ".join(e.get("message", "") for e in payload["errors"]),
            "gene": gene,
            "hgvs_protein": hgvs_protein,
            "variant_id": variant_id,
        }

    variant = (payload.get("data") or {}).get("variant")
    if not variant:
        return {
            "status": "absent",
            "reason": (
                f"Variant {gene} {hgvs_protein} (gnomAD ID {variant_id}) "
                "is absent from gnomAD v4 (~800,000 sequenced individuals). "
                "Absence is consistent with rare/pathogenic but is not "
                "proof on its own."
            ),
            "gene": gene,
            "hgvs_protein": hgvs_protein,
            "variant_id": variant_id,
            "is_rare": True,
        }

    exome = variant.get("exome") or {}
    genome = variant.get("genome") or {}
    af = max((exome.get("af") or 0.0), (genome.get("af") or 0.0))

    # Pick the consequence annotation that matches the queried gene.
    # gnomAD returns one entry per transcript, so for BRCA1 we'll see
    # several; the first match is good enough for a summary.
    consequence: str | None = None
    hgvsp_returned: str | None = None
    for tc in variant.get("transcript_consequences") or []:
        if tc.get("gene_symbol", "").upper() == gene.upper():
            consequence = tc.get("major_consequence")
            hgvsp_returned = tc.get("hgvsp")
            break

    return {
        "status": "ok",
        "variant_id": variant_id,
        "rsids": variant.get("rsids") or [],
        "consequence": consequence,
        "hgvsp": hgvsp_returned,
        "allele_frequency": af,
        "exome_ac": exome.get("ac"),
        "exome_an": exome.get("an"),
        "genome_ac": genome.get("ac"),
        "genome_an": genome.get("an"),
        "is_rare": af < COMMON_AF_THRESHOLD,
        "url": f"https://gnomad.broadinstitute.org/variant/{variant_id}",
        "gene": gene,
        "hgvs_protein": hgvs_protein,
    }


def _normalize_key(gene: str, hgvs: str) -> str:
    """Collapse 'BRCA1' + 'Cys61Gly' / 'p.Cys61Gly' / ' p.Cys61Gly '
    into the canonical 'BRCA1:p.Cys61Gly' the lookup table uses."""
    g = gene.strip().upper()
    h = hgvs.strip()
    if not h:
        return g
    # Preserve cDNA (c.5946delT) as-is; only prepend "p." for protein
    # notation that's missing it.
    if not (h.startswith("p.") or h.startswith("c.") or h.startswith("g.")):
        # Heuristic: protein notation typically has letters + digits + letters
        # ('Cys61Gly'). cDNA always starts with a digit after stripping. If
        # the first non-prefix char is a letter, treat as protein.
        h = f"p.{h}" if h[0].isalpha() else h
    return f"{g}:{h}"
