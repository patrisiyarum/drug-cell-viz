"""Sanity-check the RDKit stub docker end-to-end with a trivial fake protein."""

from __future__ import annotations

import pytest

# A minimal 5-atom "protein" PDB. Good enough to exercise the centroid math.
_FAKE_PDB = b"""ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N
ATOM      2  CA  ALA A   1       1.000   0.000   0.000  1.00  0.00           C
ATOM      3  C   ALA A   1       2.000   0.000   0.000  1.00  0.00           C
ATOM      4  O   ALA A   1       2.000   1.000   0.000  1.00  0.00           O
ATOM      5  CB  ALA A   1       1.000   1.000   0.000  1.00  0.00           C
END
"""


@pytest.mark.asyncio
async def test_dock_stub_returns_combined_pdb(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_MODAL_DOCKING", "false")
    import importlib

    from api import config as config_mod

    importlib.reload(config_mod)
    from api.services import docking as docking_mod

    importlib.reload(docking_mod)

    poses = await docking_mod.dock(_FAKE_PDB, "CCO")  # ethanol
    assert len(poses) == 1
    p = poses[0]
    assert p.confidence == 0.0
    # Combined PDB contains both the protein ATOMs and ligand HETATMs.
    assert "ATOM      1  N   ALA" in p.pose_pdb
    assert "HETATM" in p.pose_pdb


@pytest.mark.asyncio
async def test_dock_stub_rejects_invalid_smiles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_MODAL_DOCKING", "false")
    import importlib

    from api import config as config_mod

    importlib.reload(config_mod)
    from api.services import docking as docking_mod

    importlib.reload(docking_mod)

    with pytest.raises(ValueError):
        await docking_mod.dock(_FAKE_PDB, "not smiles")
