"""Download a small JUMP Cell Painting subset (~1 plate) for v1 morphology retrieval.

Pulls metadata from the `jump-cellpainting/datasets` GitHub repo and embeddings
from the public `cellpainting-gallery` S3 bucket via anonymous access.

Usage:
    uv run python scripts/download_jump_subset.py --out ./data/jump

Notes:
    - Do NOT download raw Cell Painting images. Each plate is hundreds of GB.
    - Only thumbnails + precomputed embeddings are needed.
    - S3 layout: s3://cellpainting-gallery/cpg0016-jump/source_4/workspace/profiles/...
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("./data/jump"))
    parser.add_argument("--limit-compounds", type=int, default=1000)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    # TODO(phase-3): wire up anonymous S3 via boto3 UNSIGNED and pull
    # the compound metadata + embeddings for `--limit-compounds` compounds.
    raise SystemExit("not implemented yet — wire up in Phase 3")


if __name__ == "__main__":
    main()
