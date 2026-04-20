"""Build a FAISS IndexFlatIP over JUMP Cell Painting embeddings.

Reads the downloaded subset from `scripts/download_jump_subset.py`, normalizes
vectors (L2) for inner-product-as-cosine, and writes an index + metadata sidecar
that the API loads at worker startup.

Usage:
    uv run python scripts/build_faiss_index.py --in ./data/jump --out ./data/jump/index
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    # TODO(phase-3): load embeddings parquet, faiss.normalize_L2,
    # build IndexFlatIP, serialize + write metadata sidecar.
    raise SystemExit("not implemented yet — wire up in Phase 3")


if __name__ == "__main__":
    main()
