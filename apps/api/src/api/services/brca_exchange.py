"""BRCA Exchange lookup — expert panel classifications for BRCA1/2 variants.

BRCA Exchange (brcaexchange.org) aggregates ENIGMA, ClinVar, LOVD, BIC, and
other curated sources into a single public database. The search API is free
but a bit inconsistent — it indexes on c.-notation (HGVS cDNA) and rsIDs, not
on p.-notation directly. We maintain a small p.→c. map for variants we care
about, and fall back to a free-text search otherwise.

When found, we return the ENIGMA expert classification as the authoritative
result that should outrank our ML predictor. When not found, we return None
and the UI shows only the ML card.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BRCA_EXCHANGE_URL = "https://brcaexchange.org/backend/data/"
# Hand-curated p.→c. map for our catalog variants, sourced from ClinVar +
# BRCA Exchange canonical records. Keyed on the 1-letter HGVS form our
# classifier emits.
HGVS_P_TO_C: dict[str, str] = {
    "p.C61G": "c.181T>G",
    "p.Cys61Gly": "c.181T>G",
    # Add more here as the catalog expands.
}


async def lookup(hgvs_protein: str) -> dict[str, Any] | None:
    """Return the best-match BRCA Exchange record for this p.-variant.

    Tries (in order): the hand-curated p→c map, then a free-text search on
    both p.- and c.-style queries. Returns None if nothing matches or the
    upstream call fails — never raises, because the caller uses this purely
    opportunistically.
    """
    queries: list[str] = []
    if hgvs_protein in HGVS_P_TO_C:
        queries.append(HGVS_P_TO_C[hgvs_protein])
    queries.append(hgvs_protein)
    # Also try stripping the "p." prefix — some BRCA Exchange entries index
    # the bare protein change.
    if hgvs_protein.startswith("p."):
        queries.append(hgvs_protein[2:])

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        for q in queries:
            try:
                resp = await client.get(
                    BRCA_EXCHANGE_URL,
                    params={"format": "json", "search_term": q, "page_size": 3},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.info("BRCA Exchange lookup for %r failed: %s", q, exc)
                continue
            if data.get("count", 0) <= 0:
                continue
            row = data["data"][0]
            # Only return rows that actually have an ENIGMA classification.
            if not row.get("Variant_in_ENIGMA"):
                continue
            return {
                "hgvs_cdna": row.get("HGVS_cDNA"),
                "hgvs_protein": row.get("pyhgvs_Protein") or row.get("Protein_Change"),
                "enigma_classification": row.get("Clinical_significance_ENIGMA"),
                "enigma_date_evaluated": row.get("Date_last_evaluated_ENIGMA"),
                "enigma_method": row.get("Assertion_method_ENIGMA"),
                "clinvar_classification": row.get("Clinical_Significance_ClinVar"),
                "sources": row.get("Source"),
                "link": f"https://brcaexchange.org/variant/{row.get('id')}",
                "matched_query": q,
            }
    return None
