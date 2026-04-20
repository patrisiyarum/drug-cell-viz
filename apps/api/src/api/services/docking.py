"""Ligand docking.

Phase 1 (default): an RDKit-based stub. It generates a 3D conformer from the
ligand SMILES, translates the ligand to the protein centroid, and emits a
combined PDB (protein + ligand HETATM block). This is not a real docking
result — confidence is 0.0 — but it proves the whole pipeline end to end.

Phase 2: when `settings.use_modal_docking` is true, we call a deployed Modal
function (`infra/modal/diffdock_fn.py`) that runs DiffDock on an A10G. The
wire format is strings on both sides so the call is trivially serializable.
"""

from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

from api.config import settings

logger = logging.getLogger(__name__)


@dataclass
class DockResult:
    """Raw docking output before storage. One entry per pose."""

    pose_pdb: str         # complete PDB: protein + ligand as HETATM
    confidence: float     # 0..1 (DiffDock confidence) — 0.0 for the stub


async def dock(protein_pdb: bytes, smiles: str) -> list[DockResult]:
    if settings.use_modal_docking:
        return await _dock_via_modal(protein_pdb.decode("utf-8"), smiles)
    return await asyncio.to_thread(_dock_stub, protein_pdb, smiles)


def _dock_stub(protein_pdb: bytes, smiles: str) -> list[DockResult]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"invalid SMILES: {smiles!r}")
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
        # Fallback: try a more permissive embed
        if AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=42) != 0:
            raise RuntimeError("RDKit failed to embed ligand conformer")
    try:
        AllChem.MMFFOptimizeMolecule(mol)
    except Exception as exc:  # pragma: no cover — geometry opt is best-effort
        logger.warning("MMFF optimize failed, continuing with embedded conformer: %s", exc)

    centroid = _protein_centroid(protein_pdb)
    conf = mol.GetConformer()
    ligand_center = np.mean(
        np.array([list(conf.GetAtomPosition(i)) for i in range(mol.GetNumAtoms())]),
        axis=0,
    )
    translation = centroid - ligand_center
    for i in range(mol.GetNumAtoms()):
        p = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, (p.x + translation[0], p.y + translation[1], p.z + translation[2]))

    ligand_pdb = Chem.MolToPDBBlock(mol, flavor=4)  # flavor=4 → use HETATM
    combined = _combine_pdb(protein_pdb.decode("utf-8", errors="replace"), ligand_pdb)
    return [DockResult(pose_pdb=combined, confidence=0.0)]


def _protein_centroid(pdb_bytes: bytes) -> np.ndarray:
    coords: list[tuple[float, float, float]] = []
    for raw in pdb_bytes.decode("utf-8", errors="replace").splitlines():
        if raw.startswith("ATOM  "):
            try:
                x = float(raw[30:38])
                y = float(raw[38:46])
                z = float(raw[46:54])
            except ValueError:
                continue
            coords.append((x, y, z))
    if not coords:
        raise ValueError("protein PDB had no ATOM records")
    return np.mean(np.array(coords), axis=0)


def _combine_pdb(protein_pdb: str, ligand_pdb: str) -> str:
    """Concatenate protein ATOMs and ligand HETATMs into one PDB."""
    out = io.StringIO()
    for line in protein_pdb.splitlines():
        if line.startswith(("END", "CONECT")):
            continue
        out.write(line + "\n")
    for line in ligand_pdb.splitlines():
        if line.startswith(("ATOM  ", "HETATM")):
            # Rewrite the ATOM records from RDKit into HETATM so the viewer
            # distinguishes them from the protein chain.
            if line.startswith("ATOM  "):
                line = "HETATM" + line[6:]
            out.write(line + "\n")
    out.write("END\n")
    return out.getvalue()


async def _dock_via_modal(protein_pdb: str, smiles: str) -> list[DockResult]:
    # Import inside the branch so the base image doesn't need `modal`.
    import modal  # type: ignore[import-not-found]

    fn = modal.Function.lookup(settings.modal_app_name, settings.modal_diffdock_fn)
    try:
        payload = await asyncio.wait_for(
            fn.remote.aio(protein_pdb, smiles),
            timeout=60 * 5,
        )
    except asyncio.TimeoutError as exc:
        raise RuntimeError("DiffDock timed out after 5 minutes") from exc

    poses: list[str] = payload["poses"]
    confidences: list[float] = payload["confidences"]
    return [DockResult(pose_pdb=p, confidence=c) for p, c in zip(poses, confidences, strict=True)]
