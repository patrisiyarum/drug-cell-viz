"""Wrap the HRDetect-style scar scorer in a Snakemake-friendly shim.

Reads the feature JSON produced by `extract_hrd_features.py` and writes
the full `HrdScarScore` as JSON for downstream reporting.

Pure Python / pure I/O; the actual scoring logic lives in
`api.services.hrd_scars` so the API endpoint and the pipeline share it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from api.services.hrd_scars import HrdScarFeatures, score

sm = globals().get("snakemake")
logger = logging.getLogger("hrd_scars")


def main() -> None:
    if sm is None:
        raise SystemExit("this script is meant to run via Snakemake")
    logging.basicConfig(
        filename=str(sm.log[0]) if sm.log else None,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    feat = json.loads(Path(sm.input.features).read_text())
    result = score(
        HrdScarFeatures(
            loh=int(feat["loh"]),
            lst=int(feat["lst"]),
            ntai=int(feat["ntai"]),
        )
    )

    out_path = Path(sm.output.report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # asdict doesn't traverse frozen dataclasses with list[str]; manually
    # serialise so the JSON is shape-stable.
    payload = {
        "features": asdict(result.features),
        "hrd_sum": result.hrd_sum,
        "label": result.label,
        "summary": result.summary,
        "interpretation": result.interpretation,
        "caveats": result.caveats,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    logger.info("scored sample: label=%s sum=%d", result.label, result.hrd_sum)


if __name__ == "__main__":
    main()
