"""Modal GPU function for DiffDock inference.

Deployed separately from the API container. The API invokes it via
`modal.Function.lookup(MODAL_APP_NAME, MODAL_DIFFDOCK_FN)`.

Input: protein PDB contents (str) + ligand SMILES (str).
Output: list of pose PDB contents (str) + confidence scores (list[float]).

Keeping the interface string-based (not file-based) makes it serializable
across Modal's wire protocol.
"""

from __future__ import annotations

import modal

app = modal.App("drug-cell-viz")

# TODO(phase-2): pin DiffDock to a specific commit SHA — main drifts.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("requirements.txt")
)


@app.function(image=image, gpu="A10G", timeout=60 * 10)
def dock_ligand(protein_pdb: str, smiles: str) -> dict[str, list[str] | list[float]]:
    """Dock `smiles` into `protein_pdb`. Returns top-5 poses + confidences."""
    # TODO(phase-2): invoke DiffDock inference, return dict with keys:
    #   "poses":        list[str]   # PDB contents, one per pose
    #   "confidences":  list[float] # DiffDock confidence score per pose
    raise NotImplementedError("wire up in Phase 2")
