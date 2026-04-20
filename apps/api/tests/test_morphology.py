"""Morphology service is the only piece that runs with no external services.
This test exercises the RDKit fingerprint path + SVG thumbnail rendering end
to end, which catches regressions in the most-moving service code without
needing Redis, Postgres, or network access.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_morphology_query_returns_ranked_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    # Point storage at an isolated tmpdir before importing the service.
    tmp = Path(tempfile.mkdtemp(prefix="dcv-test-"))
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp))
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://test.invalid")

    # Re-import settings + services so the env var takes effect.
    import importlib

    from api import config as config_mod

    importlib.reload(config_mod)
    from api.services import morphology as morph_mod
    from api.services import storage as storage_mod

    importlib.reload(storage_mod)
    importlib.reload(morph_mod)

    imatinib = (
        "CC1=C(C=C(C=C1)NC(=O)C2=CC=C(C=C2)CN3CCN(CC3)C)"
        "NC4=NC=CC(=N4)C5=CN=CC=C5"
    )
    fp_hex, matches, control_url = await morph_mod.query(imatinib, k=5)

    assert len(fp_hex) == 32
    assert len(matches) == 5
    # Matches are ranked by similarity descending.
    sims = [m.similarity for m in matches]
    assert sims == sorted(sims, reverse=True)
    # Identical SMILES should produce similarity == 1.0 at the top.
    top = matches[0]
    assert top.similarity > 0.99
    assert top.compound_name == "Imatinib"
    # Control thumbnail URL points at our stubbed public base.
    assert control_url.startswith("http://test.invalid/blobs/morphology/thumbnails/")


@pytest.mark.asyncio
async def test_morphology_rejects_invalid_smiles() -> None:
    from api.services import morphology as morph_mod

    with pytest.raises(ValueError):
        await morph_mod.query("not a molecule at all", k=3)
