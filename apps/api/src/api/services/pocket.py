"""Pocket-proximity analysis.

Given a protein+ligand combined PDB and a set of residue positions, compute
the minimum distance from each residue's heavy atoms to any ligand heavy atom.
If the minimum distance is ≤ POCKET_RADIUS (default 5 Å), the residue is
considered "in the binding pocket" — meaning a mutation there is likely to
perturb binding.

This is a structural heuristic, not a binding-affinity calculation. It answers
"is this variant residue physically close to where the drug sits?" — which is
the single most useful question to ask structurally without running a full
docking re-score.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

POCKET_RADIUS_ANGSTROM = 5.0


@dataclass(frozen=True)
class ResidueDistance:
    position: int  # 1-indexed residue number
    wildtype_aa: str | None
    min_distance: float


def parse_atoms(pdb_text: str) -> tuple[dict[int, list[np.ndarray]], np.ndarray, dict[int, str]]:
    """Return (protein_atoms_by_residue, ligand_atoms, residue_aa_by_position).

    `protein_atoms_by_residue`: residue number → list of xyz arrays (heavy atoms only).
    `ligand_atoms`: Nx3 array of ligand heavy-atom coordinates (HETATM records,
        excluding waters HOH).
    `residue_aa_by_position`: residue number → 3-letter residue name.
    """
    protein: dict[int, list[np.ndarray]] = {}
    ligand: list[np.ndarray] = []
    aa_by_pos: dict[int, str] = {}

    for line in pdb_text.splitlines():
        if not line.startswith(("ATOM  ", "HETATM")):
            continue
        try:
            atom_name = line[12:16].strip()
            res_name = line[17:20].strip()
            res_seq = int(line[22:26])
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
        except (ValueError, IndexError):
            continue

        # Heavy atoms only: skip hydrogens.
        if atom_name.startswith("H") or (len(atom_name) > 1 and atom_name[0].isdigit()
                                         and atom_name[1] == "H"):
            continue

        coord = np.array([x, y, z], dtype=np.float64)
        if line.startswith("ATOM  "):
            protein.setdefault(res_seq, []).append(coord)
            aa_by_pos.setdefault(res_seq, res_name)
        else:  # HETATM
            if res_name == "HOH":
                continue
            ligand.append(coord)

    lig_array = np.vstack(ligand) if ligand else np.zeros((0, 3))
    return protein, lig_array, aa_by_pos


def compute_distances(
    pdb_text: str,
    residue_positions: list[int],
) -> list[ResidueDistance]:
    """Compute min distance from each requested residue to any ligand atom.

    Returns one entry per unique position; residues absent from the PDB return
    ``min_distance = inf`` and ``wildtype_aa = None``.
    """
    protein, ligand, aa_by_pos = parse_atoms(pdb_text)
    results: list[ResidueDistance] = []
    seen: set[int] = set()

    for pos in residue_positions:
        if pos in seen:
            continue
        seen.add(pos)
        atoms = protein.get(pos)
        if not atoms or ligand.shape[0] == 0:
            results.append(
                ResidueDistance(position=pos, wildtype_aa=_three_to_one(aa_by_pos.get(pos)), min_distance=float("inf"))
            )
            continue
        coords = np.vstack(atoms)  # N x 3
        # Pairwise distances protein[N] × ligand[M] → min.
        diffs = coords[:, None, :] - ligand[None, :, :]
        dists = np.linalg.norm(diffs, axis=2)
        results.append(
            ResidueDistance(
                position=pos,
                wildtype_aa=_three_to_one(aa_by_pos.get(pos)),
                min_distance=float(dists.min()),
            )
        )
    return results


_THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}


def _three_to_one(three: str | None) -> str | None:
    if three is None:
        return None
    return _THREE_TO_ONE.get(three.upper())
