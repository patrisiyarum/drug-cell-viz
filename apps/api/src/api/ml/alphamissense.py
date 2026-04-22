"""AlphaMissense lookup for BRCA1.

Loads the precomputed AlphaMissense pathogenicity score for any BRCA1 missense
substitution from a bundled TSV. Covers every possible single amino-acid
substitution in the canonical isoform (UniProt P38398, 1863 aa × 20 AAs =
~35k scores).

AlphaMissense attribution: DeepMind, 2023 (Science, doi:10.1126/science.adg7492).
License: CC BY-NC-SA 4.0. The file header retains the copyright notice.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
DATA_PATH = HERE / "data" / "alphamissense_brca1.tsv"


@lru_cache(maxsize=1)
def _load_table() -> dict[str, tuple[float, str]]:
    """Return {protein_variant: (pathogenicity, class)} — e.g. {"C61G": (0.98, "pathogenic")}.

    Lazily loaded; trades ~2 MB of memory for O(1) lookups.
    """
    df = pd.read_csv(DATA_PATH, sep="\t", comment="#")
    # Columns: uniprot_id, protein_variant, am_pathogenicity, am_class
    # protein_variant is like "C61G" (1-letter ref + position + 1-letter alt)
    return {
        row["protein_variant"]: (
            float(row["am_pathogenicity"]),
            str(row["am_class"]),
        )
        for _, row in df.iterrows()
    }


def lookup(ref_aa: str, position: int, alt_aa: str) -> tuple[float, str] | None:
    """Return (pathogenicity, class) for a BRCA1 variant, or None if not in table.

    AlphaMissense only scores missense substitutions (ref != alt, no stops).
    For synonymous/nonsense we return None and the ensemble falls back to the
    XGBoost prediction alone.
    """
    if ref_aa == alt_aa or alt_aa == "*":
        return None
    key = f"{ref_aa}{position}{alt_aa}"
    return _load_table().get(key)
