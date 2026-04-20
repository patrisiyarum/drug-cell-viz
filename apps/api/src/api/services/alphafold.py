"""Fetch protein structures from the AlphaFold DB, cached in blob storage."""

from __future__ import annotations

import logging

import httpx

from api.services import storage

logger = logging.getLogger(__name__)

_API_URL = "https://alphafold.ebi.ac.uk/api/prediction/{uniprot_id}"


class AlphaFoldNotFound(Exception):
    """Raised when the AlphaFold DB has no prediction for a UniProt ID."""


async def fetch_structure(uniprot_id: str) -> tuple[bytes, str]:
    """Return (pdb_bytes, public_url) for `uniprot_id`. Caches in blob storage.

    The AlphaFold DB assigns one deterministic prediction per UniProt entry, so
    we key the cache purely on the UniProt ID.
    """
    key = f"alphafold/{uniprot_id}.pdb"
    cached = await storage.get(key)
    if cached is not None:
        url = await storage.put(key, cached, "chemical/x-pdb")
        return cached, url

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        meta = await client.get(_API_URL.format(uniprot_id=uniprot_id))
        if meta.status_code == 404:
            raise AlphaFoldNotFound(f"no AlphaFold prediction for {uniprot_id}")
        meta.raise_for_status()
        payload = meta.json()
        if not payload:
            raise AlphaFoldNotFound(f"no AlphaFold prediction for {uniprot_id}")
        pdb_url = payload[0].get("pdbUrl")
        if not pdb_url:
            raise AlphaFoldNotFound(f"AlphaFold payload missing pdbUrl for {uniprot_id}")

        pdb_resp = await client.get(pdb_url)
        pdb_resp.raise_for_status()
        pdb_bytes = pdb_resp.content

    url = await storage.put(key, pdb_bytes, "chemical/x-pdb")
    logger.info("alphafold cached %s (%d bytes)", uniprot_id, len(pdb_bytes))
    return pdb_bytes, url
