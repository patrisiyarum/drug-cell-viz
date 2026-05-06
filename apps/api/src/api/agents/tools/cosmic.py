"""COSMIC (Catalogue of Somatic Mutations in Cancer) lookup.

COSMIC's modern API requires an institutional or personal access token
(register at https://cancer.sanger.ac.uk/cosmic). When the token is
present we hit their search endpoint; when it isn't, this tool returns
a structured "data unavailable, requires registration" response that
the agent can surface honestly to the user.

COSMIC's value-add over ClinVar: somatic-mutation context. ClinVar tells
you "is this variant pathogenic in a clinical-genetics sense?" COSMIC
tells you "how many tumor samples in our database have this exact change,
and which cancer types?" Recurrence in cancer tissue is independent
evidence from germline pathogenicity classification.

Honest caveat the agent surfaces: COSMIC's coverage is biased toward
well-studied cancers and well-funded labs. Absence of a hit doesn't
prove rarity — it might mean the variant just hasn't been sequenced in
COSMIC's contributor cohort yet.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# The COSMIC API moved to a token-gated v98+ endpoint. Public legacy
# endpoints used to exist; they're shut down. We attempt the new endpoint
# only when the env var is set; otherwise we return a clear "auth needed"
# response so the agent's downstream synthesis can mention the gap
# without pretending it has data.
COSMIC_TOKEN_ENV = "COSMIC_API_TOKEN"
COSMIC_BASE = "https://cancer.sanger.ac.uk/cosmic-api"  # current as of 2026
TIMEOUT = httpx.Timeout(15.0, connect=5.0)


async def lookup_variant(gene: str, hgvs_protein: str) -> dict[str, Any]:
    """Look up a variant's somatic-mutation frequency in COSMIC.

    Args:
        gene: HGNC gene symbol
        hgvs_protein: HGVS protein notation

    Returns:
        Dict with status + (when available) frequency_in_cancer fields,
        or a structured "auth required" stub.
    """
    token = os.environ.get(COSMIC_TOKEN_ENV, "").strip()
    if not token:
        return {
            "status": "auth_required",
            "reason": (
                "COSMIC API requires a personal access token "
                f"(env: {COSMIC_TOKEN_ENV}). Register at "
                "cancer.sanger.ac.uk/cosmic to obtain one. The agent will "
                "synthesize using the other three sources."
            ),
            "gene": gene,
            "hgvs_protein": hgvs_protein,
        }

    # Real API call when the token is set. The exact endpoint shape
    # depends on COSMIC's v98 contract; this is the documented path for
    # mutation search by AA change. If the call fails or 401s, we surface
    # the error rather than fabricate data.
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": f"{gene} {hgvs_protein}", "format": "json"}

    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
        try:
            r = await client.get(f"{COSMIC_BASE}/search/mutation", params=params)
            r.raise_for_status()
            payload = r.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("COSMIC lookup failed for %s %s: %s", gene, hgvs_protein, exc)
            return {
                "status": "error",
                "reason": f"COSMIC API call failed: {exc}",
                "gene": gene,
                "hgvs_protein": hgvs_protein,
            }

    hits = payload.get("hits") or []
    if not hits:
        return {
            "status": "not_found",
            "reason": (
                f"No COSMIC record matched {gene} {hgvs_protein}. The "
                "variant may not be present in COSMIC's curated tumor "
                "samples — note this is sampling bias, not a guarantee "
                "that the variant is rare in cancer."
            ),
            "gene": gene,
            "hgvs_protein": hgvs_protein,
        }

    # Aggregate the most useful summary stats across all hits for this
    # AA change. Different transcript-level descriptions of the same
    # protein change can produce multiple hits in COSMIC.
    total_samples = sum(h.get("sample_count", 0) for h in hits)
    by_cancer: dict[str, int] = {}
    for h in hits:
        for tissue in (h.get("primary_tissue_distribution") or []):
            t = tissue.get("name", "unknown")
            by_cancer[t] = by_cancer.get(t, 0) + tissue.get("sample_count", 0)

    top_cancers = sorted(by_cancer.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return {
        "status": "ok",
        "total_samples": total_samples,
        "top_cancer_types": [{"name": n, "samples": s} for n, s in top_cancers],
        "hit_count": len(hits),
        "url": f"https://cancer.sanger.ac.uk/cosmic/search?q={gene}+{hgvs_protein}",
        "gene": gene,
        "hgvs_protein": hgvs_protein,
    }
