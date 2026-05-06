"""ClinVar lookup via NCBI E-utilities.

ClinVar is the canonical clinical-variant interpretation database. We use
NCBI's public E-utilities API (no auth required, optional NCBI_API_KEY for
higher rate limits). The flow is two calls:

    1. esearch — find the ClinVar variation_id for a (gene, HGVS) pair
    2. esummary — pull the structured record for that variation_id

The returned dict is intentionally narrow — only the fields a clinician or
patient cares about: significance, review status, conditions, last update,
and a stable URL the user can click through to see the full record.

Why we surface review_status: it's the credibility signal. A "criteria
provided, multiple submitters, no conflicts" rating means human curators
agreed; a "no assertion criteria provided" rating means it's a single
submitter's opinion. Treating both as equal is medically irresponsible.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)


async def lookup_variant(gene: str, hgvs_protein: str) -> dict[str, Any]:
    """Look up a single variant in ClinVar.

    Args:
        gene: HGNC gene symbol (e.g. "BRCA1")
        hgvs_protein: HGVS protein notation (e.g. "p.Cys61Gly" or "Cys61Gly")

    Returns:
        Dict with keys: status, variation_id, significance, review_status,
        conditions, url, raw_term. When the lookup fails the status is set
        to "not_found" / "error" with a human-readable reason.
    """
    api_key = os.environ.get("NCBI_API_KEY", "").strip() or None

    # Normalize: ClinVar's text search wants "BRCA1 Cys61Gly" or
    # "BRCA1 p.Cys61Gly" — both work. We pass the user's input through.
    hgvs = hgvs_protein.lstrip()
    term = f"{gene}[gene] AND {hgvs}"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Step 1: esearch -> uid
        try:
            r = await client.get(
                f"{NCBI_BASE}/esearch.fcgi",
                params=_with_key({
                    "db": "clinvar",
                    "term": term,
                    "retmode": "json",
                }, api_key),
            )
            r.raise_for_status()
            esearch = r.json().get("esearchresult", {})
            uids = esearch.get("idlist") or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("ClinVar esearch failed for %s %s: %s", gene, hgvs, exc)
            return _err(f"ClinVar lookup failed: {exc}", gene, hgvs)

        if not uids:
            return {
                "status": "not_found",
                "reason": (
                    f"No ClinVar record matched '{term}'. The variant may not "
                    "be cataloged or the HGVS string may need normalization."
                ),
                "raw_term": term,
                "gene": gene,
                "hgvs_protein": hgvs,
            }

        uid = uids[0]

        # Step 2: esummary -> structured record
        try:
            r = await client.get(
                f"{NCBI_BASE}/esummary.fcgi",
                params=_with_key({
                    "db": "clinvar",
                    "id": uid,
                    "retmode": "json",
                }, api_key),
            )
            r.raise_for_status()
            payload = r.json().get("result", {}).get(uid, {}) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("ClinVar esummary failed for uid=%s: %s", uid, exc)
            return _err(f"ClinVar esummary failed: {exc}", gene, hgvs)

    # Pull just the fields the agent actually uses. Keeping the payload
    # narrow avoids bloating Claude's context window with raw API noise.
    germline = (payload.get("germline_classification") or {})
    conditions_raw = germline.get("trait_set") or []
    conditions = [
        c.get("trait_name") for c in conditions_raw if c.get("trait_name")
    ]

    return {
        "status": "ok",
        "variation_id": uid,
        "title": payload.get("title", ""),
        "significance": germline.get("description"),
        "review_status": germline.get("review_status"),
        "last_evaluated": germline.get("last_evaluated"),
        "conditions": conditions,
        "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{uid}/",
        "raw_term": term,
        "gene": gene,
        "hgvs_protein": hgvs,
    }


def _with_key(params: dict[str, str], api_key: str | None) -> dict[str, str]:
    if api_key:
        params["api_key"] = api_key
    return params


def _err(reason: str, gene: str, hgvs: str) -> dict[str, Any]:
    return {
        "status": "error",
        "reason": reason,
        "gene": gene,
        "hgvs_protein": hgvs,
    }
