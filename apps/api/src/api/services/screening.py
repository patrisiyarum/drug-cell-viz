"""In-silico virtual screening: rank a library of candidate compounds against
an HR-panel target by how well each fits the binding pocket.

This mirrors the core Bioptic product story at a miniature scale — take a
target protein, take a compound library, do the chemistry on a computer before
ever touching the wet lab. The scoring is deliberately two-part so neither
signal alone can dominate:

  1. `pocket_fit`    — fraction of the docked ligand's heavy atoms that sit
                       within POCKET_RADIUS of any protein atom. Directly
                       measures whether the compound fits *into* the binding
                       cleft rather than flapping around on the surface.

  2. `chem_similarity` — Tanimoto similarity (Morgan r=2) to the closest known
                        binder of this target. A compound that looks like
                        olaparib is a better PARP1 lead than one that looks
                        like aspirin, even before docking it.

Composite `fit_score` = 0.6 * pocket_fit + 0.4 * chem_similarity.

The underlying docking is the same RDKit stub / Modal DiffDock adapter used
by the single-compound analysis; docking is already async so we parallelize
the per-candidate calls with asyncio.gather.

Intended audience: patients / researchers exploring why a given drug class
(PARP inhibitors, SERDs, CDK4/6 inhibitors) makes sense for a given HR-panel
target, and for head-to-head comparisons across a small compound library.
Not a replacement for a real structure-based virtual screen.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem

from api.services import alphafold, docking
from api.services.bc_catalog import DRUGS, GENES
from api.services.pocket import POCKET_RADIUS_ANGSTROM, parse_atoms

logger = logging.getLogger(__name__)


class ScreeningError(ValueError):
    pass


# Curated reference binders per target. These are the canonical compounds
# whose SMILES we trust to represent the chemical space a new candidate
# should resemble to plausibly hit this protein. Sourced from the catalog
# plus a handful of additional well-known PARP / SERM / CDK4/6 leads.
REFERENCE_BINDERS: dict[str, list[tuple[str, str]]] = {
    "PARP1": [
        ("olaparib", DRUGS["olaparib"]["smiles"]),
        ("niraparib", DRUGS["niraparib"]["smiles"]),
        # talazoparib — FDA-approved PARPi we don't have in the main catalog
        ("talazoparib", "C1CC2=C(C1=O)C3=CC(=CC=C3N=C2C4=CC=C(C=C4)F)C5=NNC=N5"),
        # rucaparib — FDA-approved PARPi
        ("rucaparib", "CNCC1=CC=C(C=C1)C2=C3C(=CC=C2F)C(=O)NCC3"),
    ],
    "ESR1": [
        ("tamoxifen", DRUGS["tamoxifen"]["smiles"]),
        ("fulvestrant", DRUGS["fulvestrant"]["smiles"]),
        ("elacestrant", DRUGS["elacestrant"]["smiles"]),
    ],
    "CDK4": [
        ("palbociclib", DRUGS["palbociclib"]["smiles"]),
        # ribociclib — CDK4/6i (not in main catalog as a standalone entry)
        ("ribociclib", "CC1(C)c2nc3c(cnc(Nc4ccc(N5CCNCC5)cn4)n3)cc2N(C)C1=O"),
    ],
    "CDK6": [
        ("palbociclib", DRUGS["palbociclib"]["smiles"]),
    ],
    "PIK3CA": [
        ("alpelisib", DRUGS["alpelisib"]["smiles"]),
    ],
    "CYP19A1": [
        ("letrozole", DRUGS["letrozole"]["smiles"]),
    ],
    # BRCA1 / BRCA2 are not classical drug targets — they're DNA repair
    # scaffolds. Screening against BRCA1 directly makes little sense; the
    # therapeutic relationship is via synthetic lethality with PARP
    # inhibitors. We expose them here anyway because the frontend will want
    # to offer every HR-panel gene as a selectable target and we shouldn't
    # reject the request — we just return an empty REFERENCE_BINDERS slot
    # so chem_similarity falls back to 0 and pocket_fit carries the signal.
}


@dataclass(frozen=True)
class CandidateInput:
    id: str
    name: str
    smiles: str


@dataclass(frozen=True)
class CandidateScore:
    candidate_id: str
    name: str
    smiles: str
    pocket_fit: float          # 0..1 — fraction of ligand heavy atoms within POCKET_RADIUS
    chem_similarity: float     # 0..1 — max Tanimoto to reference binders
    closest_reference: str | None
    fit_score: float           # 0..1 composite
    heavy_atom_count: int
    rank: int


@dataclass(frozen=True)
class ScreeningResult:
    target_gene: str
    target_uniprot: str
    pocket_radius_angstrom: float
    reference_binders: list[str]   # names of references used for chem similarity
    ranked: list[CandidateScore]


async def run_screening(
    target_gene: str,
    candidates: list[CandidateInput],
) -> ScreeningResult:
    """Score each candidate against the target's binding pocket, return ranked."""
    if not candidates:
        raise ScreeningError("no candidates provided")

    gene_entry = GENES.get(target_gene)
    if gene_entry is None:
        raise ScreeningError(
            f"target {target_gene!r} not in curated gene list "
            f"({sorted(GENES.keys())!r})"
        )

    # Fetch the AlphaFold structure once; we reuse it across candidates.
    protein_pdb_bytes, _ = await alphafold.fetch_structure(gene_entry["uniprot_id"])

    # Pre-compute the reference fingerprints so we don't rebuild them on every
    # candidate comparison.
    ref_names, ref_fps = _reference_fingerprints(target_gene)

    # Parallelise docking across candidates — the RDKit stub is CPU-bound but
    # fast enough that gather + to_thread is fine, and Modal DiffDock will be
    # naturally concurrent.
    scores = await asyncio.gather(
        *(
            _score_candidate(protein_pdb_bytes, c, ref_names, ref_fps)
            for c in candidates
        ),
        return_exceptions=True,
    )

    valid: list[CandidateScore] = []
    for c, s in zip(candidates, scores, strict=True):
        if isinstance(s, Exception):
            logger.warning("screening: %s failed to score: %s", c.id, s)
            continue
        valid.append(s)

    if not valid:
        raise ScreeningError("every candidate failed to score; check the SMILES")

    # Rank: highest fit_score first. Break ties by pocket_fit (a physical
    # signal) over chem_similarity (a heuristic).
    ranked = sorted(
        valid,
        key=lambda s: (s.fit_score, s.pocket_fit, s.chem_similarity),
        reverse=True,
    )
    ranked = [
        CandidateScore(
            candidate_id=s.candidate_id,
            name=s.name,
            smiles=s.smiles,
            pocket_fit=s.pocket_fit,
            chem_similarity=s.chem_similarity,
            closest_reference=s.closest_reference,
            fit_score=s.fit_score,
            heavy_atom_count=s.heavy_atom_count,
            rank=i + 1,
        )
        for i, s in enumerate(ranked)
    ]

    return ScreeningResult(
        target_gene=target_gene,
        target_uniprot=gene_entry["uniprot_id"],
        pocket_radius_angstrom=POCKET_RADIUS_ANGSTROM,
        reference_binders=ref_names,
        ranked=ranked,
    )


async def _score_candidate(
    protein_pdb_bytes: bytes,
    candidate: CandidateInput,
    ref_names: list[str],
    ref_fps: list[object],
) -> CandidateScore:
    # --- pocket fit via docking ---
    poses = await docking.dock(protein_pdb_bytes, candidate.smiles)
    if not poses:
        raise ScreeningError(f"{candidate.id}: docking returned no poses")
    pose = poses[0]
    _, ligand_atoms, _ = parse_atoms(pose.pose_pdb)
    heavy_atom_count = int(ligand_atoms.shape[0])
    if heavy_atom_count == 0:
        raise ScreeningError(f"{candidate.id}: parsed pose has no ligand atoms")

    # Protein heavy atoms as a single array; distances per ligand atom.
    protein_atoms_by_res, _, _ = parse_atoms(pose.pose_pdb)
    if not protein_atoms_by_res:
        raise ScreeningError(f"{candidate.id}: parsed pose has no protein atoms")
    protein_coords = np.vstack(
        [a for atoms in protein_atoms_by_res.values() for a in atoms]
    )
    # Pairwise distances: ligand N × protein M → min along protein axis.
    diffs = ligand_atoms[:, None, :] - protein_coords[None, :, :]
    min_dists = np.linalg.norm(diffs, axis=2).min(axis=1)
    in_pocket = int((min_dists <= POCKET_RADIUS_ANGSTROM).sum())
    pocket_fit = in_pocket / heavy_atom_count

    # --- chem similarity to reference binders ---
    chem_similarity, closest_ref = _similarity_to_references(
        candidate.smiles, ref_names, ref_fps,
    )

    fit_score = 0.6 * pocket_fit + 0.4 * chem_similarity

    return CandidateScore(
        candidate_id=candidate.id,
        name=candidate.name,
        smiles=candidate.smiles,
        pocket_fit=round(pocket_fit, 4),
        chem_similarity=round(chem_similarity, 4),
        closest_reference=closest_ref,
        fit_score=round(fit_score, 4),
        heavy_atom_count=heavy_atom_count,
        rank=0,  # overwritten by caller after ranking
    )


def _reference_fingerprints(
    target_gene: str,
) -> tuple[list[str], list[object]]:
    refs = REFERENCE_BINDERS.get(target_gene, [])
    names: list[str] = []
    fps: list[object] = []
    for name, smiles in refs:
        if not smiles:
            continue
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("screening: reference %s has invalid SMILES", name)
            continue
        names.append(name)
        fps.append(AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048))
    return names, fps


def _similarity_to_references(
    smiles: str,
    ref_names: list[str],
    ref_fps: list[object],
) -> tuple[float, str | None]:
    if not ref_fps:
        return 0.0, None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return 0.0, None
    fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
    sims = [DataStructs.TanimotoSimilarity(fp, rfp) for rfp in ref_fps]
    best_idx = int(np.argmax(sims))
    return float(sims[best_idx]), ref_names[best_idx]
