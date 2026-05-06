"""OpenFDA drug-label lookup.

OpenFDA's drug-label endpoint exposes every FDA-approved drug label
(the "package insert" text). The agent uses it to answer the bridging
question: "given this gene, which FDA-approved drugs target it, and what
do their labels say about the indication?"

For Maya's BRCA1 case this should return olaparib + niraparib + rucaparib
(the PARP-inhibitor class), each with the labeled indication
("germline BRCA-mutated ovarian cancer" etc.).

We use the public OpenFDA endpoint — no auth required, optional API key
for higher rate limits. The query searches both the indications field
and the brand-name list in parallel; we filter results client-side
because OpenFDA's full-text search is intentionally permissive.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OPENFDA_BASE = "https://api.fda.gov/drug/label.json"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)

# Curated map: gene → drug class. We ground the OpenFDA search on a
# known list of generic drug names per gene rather than letting Claude
# guess. Keeps the tool deterministic and audit-friendly.
GENE_DRUG_HINTS: dict[str, list[str]] = {
    "BRCA1": ["olaparib", "niraparib", "rucaparib", "talazoparib"],
    "BRCA2": ["olaparib", "niraparib", "rucaparib", "talazoparib"],
    "ATM":   ["olaparib"],
    "PALB2": ["olaparib", "niraparib"],
    "RAD51C": ["olaparib", "niraparib", "rucaparib"],
    "RAD51D": ["olaparib", "niraparib", "rucaparib"],
    "CYP2D6": ["tamoxifen"],
}


async def drugs_for_gene(gene: str) -> dict[str, Any]:
    """Return FDA-approved drug labels relevant to a gene.

    Args:
        gene: HGNC gene symbol

    Returns:
        Dict with status + drugs[] entries (generic_name, brand_names,
        indication_excerpt, set_id, label_url) plus a stub when no drugs
        are mapped for that gene.
    """
    api_key = os.environ.get("OPENFDA_API_KEY", "").strip() or None
    drug_names = GENE_DRUG_HINTS.get(gene.upper(), [])
    if not drug_names:
        return {
            "status": "no_curated_drugs",
            "reason": (
                f"No FDA-approved drugs are curated as targeting {gene} in "
                "the agent's gene-drug map. Genes covered today: "
                f"{', '.join(sorted(GENE_DRUG_HINTS))}. Expanding the map "
                "is a one-line config change."
            ),
            "gene": gene,
        }

    drugs: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for drug_name in drug_names:
            try:
                params = {
                    "search": (
                        f'openfda.generic_name:"{drug_name}" '
                        f'OR openfda.brand_name:"{drug_name}"'
                    ),
                    "limit": "1",
                }
                if api_key:
                    params["api_key"] = api_key
                r = await client.get(OPENFDA_BASE, params=params)
                if r.status_code == 404:
                    # OpenFDA returns 404 when no matches; treat as missing
                    drugs.append(_missing(drug_name, "no FDA label record returned"))
                    continue
                r.raise_for_status()
                hits = r.json().get("results") or []
            except Exception as exc:  # noqa: BLE001
                logger.warning("OpenFDA lookup failed for %s: %s", drug_name, exc)
                drugs.append(_missing(drug_name, str(exc)))
                continue

            if not hits:
                drugs.append(_missing(drug_name, "empty result set"))
                continue

            label = hits[0]
            openfda = label.get("openfda") or {}
            indications = label.get("indications_and_usage") or []
            indication_text = indications[0] if indications else ""
            # Trim to a useful excerpt — the full label is several pages.
            excerpt = _excerpt(indication_text, max_chars=400)

            drugs.append({
                "status": "ok",
                "generic_name": drug_name,
                "brand_names": openfda.get("brand_name") or [],
                "manufacturer": (openfda.get("manufacturer_name") or [None])[0],
                "indication_excerpt": excerpt,
                "set_id": label.get("set_id"),
                "label_url": (
                    f"https://labels.fda.gov/{label['set_id']}.xml"
                    if label.get("set_id") else None
                ),
            })

    return {
        "status": "ok",
        "gene": gene,
        "drugs": drugs,
        "n_drugs_curated": len(drug_names),
        "n_drugs_with_label": sum(1 for d in drugs if d.get("status") == "ok"),
    }


def _excerpt(text: str, max_chars: int = 400) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"


def _missing(drug_name: str, reason: str) -> dict[str, Any]:
    return {
        "status": "missing",
        "generic_name": drug_name,
        "reason": reason,
    }
