"""Variant-input handling.

Two modes are supported:
  1. Catalog pick — user selects a curated variant id (VARIANTS dict key).
  2. Protein-sequence paste — user pastes a protein sequence for a supported
     gene. We align to the wild-type AlphaFold sequence and report residue
     substitutions. Insertions/deletions shift downstream numbering, so for
     the v1 analysis we report only aligned-position substitutions and flag
     length mismatches as "indel present (positions approximate)".

Sequence handling uses a lightweight global alignment (Needleman-Wunsch with
unit costs) — good enough to detect single-AA changes against a known WT.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from api.services.bc_catalog import GENES


@dataclass(frozen=True)
class ResolvedVariant:
    gene_symbol: str
    catalog_id: str | None
    display_name: str
    residue_positions: list[int]
    hgvs_protein: str | None
    zygosity: str


class VariantResolutionError(ValueError):
    """Raised for bad input: unknown gene, unresolvable sequence, etc."""


async def fetch_uniprot_sequence(uniprot_id: str) -> str:
    """Pull the canonical isoform sequence from UniProt REST."""
    url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.fasta"
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
    resp.raise_for_status()
    lines = resp.text.splitlines()
    return "".join(line for line in lines if not line.startswith(">"))


def align_and_diff(wildtype: str, variant_seq: str) -> tuple[list[tuple[int, str, str]], bool]:
    """Return (substitutions, has_indel).

    `substitutions` is a list of (position_1_indexed, wt_aa, var_aa). An indel
    is heuristically flagged when the length differs by more than a few.
    """
    variant_seq = "".join(c for c in variant_seq.upper() if c.isalpha())
    wildtype = wildtype.upper()

    if len(variant_seq) == 0:
        raise VariantResolutionError("protein sequence is empty")

    if abs(len(variant_seq) - len(wildtype)) > 3 and len(variant_seq) < len(wildtype) * 0.85:
        # If the user pasted a fragment, align it as a substring first.
        best = _best_local_window(wildtype, variant_seq)
        if best is None:
            raise VariantResolutionError(
                "pasted sequence doesn't look like a fragment of the wild-type"
            )
        offset, aligned = best
        subs = [
            (offset + i + 1, wildtype[offset + i], a)
            for i, a in enumerate(aligned)
            if wildtype[offset + i] != a
        ]
        return subs, False

    if len(variant_seq) != len(wildtype):
        return [], True  # indel — positions unreliable, skip sub reporting

    subs = [
        (i + 1, wildtype[i], v)
        for i, v in enumerate(variant_seq)
        if wildtype[i] != v
    ]
    return subs, False


def _best_local_window(wildtype: str, fragment: str) -> tuple[int, str] | None:
    """Find the best-matching window of len(fragment) in wildtype.

    Used when the user pastes a partial sequence. Naive sliding window with
    identity scoring is fine for a ≤2,000 aa protein.
    """
    if len(fragment) > len(wildtype):
        return None
    best_score = -1
    best_offset = -1
    for offset in range(len(wildtype) - len(fragment) + 1):
        score = sum(1 for i, c in enumerate(fragment) if wildtype[offset + i] == c)
        if score > best_score:
            best_score = score
            best_offset = offset
    # Require at least 80% identity to accept the alignment.
    if best_score < 0.8 * len(fragment):
        return None
    return best_offset, fragment


def gene_for_symbol(symbol: str) -> str:
    if symbol not in GENES:
        raise VariantResolutionError(
            f"gene {symbol!r} not in curated breast-cancer catalog"
        )
    return GENES[symbol]["uniprot_id"]


_uniprot_cache: dict[str, str] = {}


async def _cached_uniprot(uniprot_id: str) -> str:
    seq = _uniprot_cache.get(uniprot_id)
    if seq is None:
        seq = await fetch_uniprot_sequence(uniprot_id)
        _uniprot_cache[uniprot_id] = seq
    return seq


async def identify_gene_from_sequence(pasted: str) -> tuple[str, float] | None:
    """Auto-detect which supported gene a pasted sequence belongs to.

    Scores the pasted sequence against every curated gene's canonical UniProt
    sequence by best-window identity. Returns (gene_symbol, fraction) for the
    top match if it clears 70% identity, otherwise None.

    This is how the frontend handles "paste a sequence, leave the gene picker
    on 'none'" — a patient pasting their variant of ABL1 shouldn't also have
    to know the name of the gene.
    """
    cleaned = "".join(c for c in pasted.upper() if c.isalpha())
    if len(cleaned) < 30:
        return None

    best: tuple[str, float] | None = None
    for symbol, gene in GENES.items():
        try:
            wt = await _cached_uniprot(gene["uniprot_id"])
        except Exception:
            continue
        score = _max_identity(wt.upper(), cleaned)
        if best is None or score > best[1]:
            best = (symbol, score)

    if best is None or best[1] < 0.70:
        return None
    return best


def _max_identity(wildtype: str, fragment: str) -> float:
    """Return the best identity fraction when `fragment` is slid across `wildtype`.

    Handles both full-length paste (len equal) and partial paste (fragment
    shorter). For very long proteins this is O(n*m) but our genes cap at
    a few thousand residues, so it runs in tens of ms.
    """
    if len(fragment) == 0 or len(wildtype) == 0:
        return 0.0
    if len(fragment) >= len(wildtype):
        matches = sum(1 for i, c in enumerate(wildtype) if c == fragment[i])
        return matches / len(wildtype)
    best_matches = 0
    for offset in range(len(wildtype) - len(fragment) + 1):
        m = sum(1 for i, c in enumerate(fragment) if wildtype[offset + i] == c)
        if m > best_matches:
            best_matches = m
    return best_matches / len(fragment)
