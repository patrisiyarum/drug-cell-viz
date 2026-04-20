"""Bundled JUMP-CP-style compound catalog for the morphology baseline.

This is a small curated set of reference compounds used in the v1 retrieval
baseline. In production you replace this with the output of
`scripts/download_jump_subset.py` + `scripts/build_faiss_index.py`, which pull
the real JUMP Cell Painting embeddings and metadata.

Thumbnails are rendered server-side as SVG placeholders that include the
compound name, cell line, and dose — so the UX is demoable without the ~GB
download. When the real index is wired up, the `image_url` field will point at
R2-hosted PNG thumbnails of CellProfiler-composed RGB images.
"""

from __future__ import annotations

from typing import TypedDict


class CatalogEntry(TypedDict):
    broad_sample_id: str
    compound_name: str
    smiles: str
    cell_line: str
    dose_um: float | None
    phenotype_tag: str  # short human label for the placeholder thumbnail


CATALOG: list[CatalogEntry] = [
    {
        "broad_sample_id": "BRD-K92723993",
        "compound_name": "DMSO (control)",
        "smiles": "CS(=O)C",
        "cell_line": "U2OS",
        "dose_um": 0.0,
        "phenotype_tag": "control",
    },
    {
        "broad_sample_id": "BRD-K11853681",
        "compound_name": "Imatinib",
        "smiles": "CC1=C(C=C(C=C1)NC(=O)C2=CC=C(C=C2)CN3CCN(CC3)C)NC4=NC=CC(=N4)C5=CN=CC=C5",
        "cell_line": "U2OS",
        "dose_um": 10.0,
        "phenotype_tag": "kinase-inhibitor",
    },
    {
        "broad_sample_id": "BRD-K27188169",
        "compound_name": "Gefitinib",
        "smiles": "COC1=C(C=C2C(=C1)N=CN=C2NC3=CC(=C(C=C3)F)Cl)OCCCN4CCOCC4",
        "cell_line": "U2OS",
        "dose_um": 10.0,
        "phenotype_tag": "kinase-inhibitor",
    },
    {
        "broad_sample_id": "BRD-K23984367",
        "compound_name": "Erlotinib",
        "smiles": "COCCOC1=C(C=C2C(=C1)N=CN=C2NC3=CC=CC(=C3)C#C)OCCOC",
        "cell_line": "U2OS",
        "dose_um": 10.0,
        "phenotype_tag": "kinase-inhibitor",
    },
    {
        "broad_sample_id": "BRD-K56343971",
        "compound_name": "Dasatinib",
        "smiles": "CC1=C(C(=CC=C1)Cl)NC(=O)C2=CN=C(S2)NC3=CC(=NC(=N3)C)N4CCN(CC4)CCO",
        "cell_line": "U2OS",
        "dose_um": 10.0,
        "phenotype_tag": "kinase-inhibitor",
    },
    {
        "broad_sample_id": "BRD-K24575266",
        "compound_name": "Paclitaxel",
        "smiles": "CC1=C2C(C(=O)C3(C(CC4C(C3C(C(C2(C)C)(CC1OC(=O)C(C(C5=CC=CC=C5)NC(=O)C6=CC=CC=C6)O)O)OC(=O)C)(CO4)OC(=O)C)O)C)OC(=O)C",
        "cell_line": "U2OS",
        "dose_um": 1.0,
        "phenotype_tag": "microtubule",
    },
    {
        "broad_sample_id": "BRD-K70301465",
        "compound_name": "Vincristine",
        "smiles": "CCC1(CC2CC(C3=C(CCN(C2)C1)C4=CC=CC=C4N3)(C5=C(C=C6C(=C5)C78CCN9C7C(C=CC9)(C(C(C8N6C)(C(=O)OC)O)OC(=O)C)CC)OC)C(=O)OC)O",
        "cell_line": "U2OS",
        "dose_um": 1.0,
        "phenotype_tag": "microtubule",
    },
    {
        "broad_sample_id": "BRD-K50799972",
        "compound_name": "Nocodazole",
        "smiles": "COC(=O)NC1=NC2=C(N1)C=C(C=C2)C(=O)C3=CC=CS3",
        "cell_line": "U2OS",
        "dose_um": 3.0,
        "phenotype_tag": "microtubule",
    },
    {
        "broad_sample_id": "BRD-K07442505",
        "compound_name": "Staurosporine",
        "smiles": "CNC1CC2OC(C3=C2C4=C(C5=CC=CC=C51)C6=CC=CC=C6N4C3)C",
        "cell_line": "U2OS",
        "dose_um": 1.0,
        "phenotype_tag": "kinase-inhibitor",
    },
    {
        "broad_sample_id": "BRD-K60230970",
        "compound_name": "Doxorubicin",
        "smiles": "CC1C(C(CC(O1)OC2CC(CC3=C2C(=C4C(=C3O)C(=O)C5=C(C4=O)C=CC=C5OC)O)(C(=O)CO)O)N)O",
        "cell_line": "U2OS",
        "dose_um": 1.0,
        "phenotype_tag": "DNA-damage",
    },
    {
        "broad_sample_id": "BRD-K65503129",
        "compound_name": "Etoposide",
        "smiles": "CC1OCC2C(O1)C(C(C(O2)OC3C4COC(=O)C4C(C5=CC6=C(C=C35)OCO6)C7=CC(=C(C(=C7)OC)O)OC)O)O",
        "cell_line": "U2OS",
        "dose_um": 10.0,
        "phenotype_tag": "DNA-damage",
    },
    {
        "broad_sample_id": "BRD-K60230970-2",
        "compound_name": "Cycloheximide",
        "smiles": "CC1CC(=O)CC(C1CC2CC(=O)NC(=O)C2)O",
        "cell_line": "U2OS",
        "dose_um": 10.0,
        "phenotype_tag": "translation-inhibitor",
    },
    {
        "broad_sample_id": "BRD-K47549133",
        "compound_name": "Rapamycin",
        "smiles": "CC1CCC2CC(C(=CC=CC=CC(CC(C(=O)C(C(C(=CC(C(=O)CC(OC(=O)C3CCCCN3C(=O)C(=O)C1(O2)O)C(C)CC4CCC(C(C4)OC)O)C)C)O)OC)C)C)C)OC",
        "cell_line": "U2OS",
        "dose_um": 1.0,
        "phenotype_tag": "mTOR-inhibitor",
    },
    {
        "broad_sample_id": "BRD-K28923025",
        "compound_name": "Tubastatin A",
        "smiles": "C1CC2=C(CN1CC3=CC=C(C=C3)C(=O)NO)C4=CC=CC=C4N2",
        "cell_line": "U2OS",
        "dose_um": 10.0,
        "phenotype_tag": "HDAC-inhibitor",
    },
    {
        "broad_sample_id": "BRD-K04046242",
        "compound_name": "Latrunculin B",
        "smiles": "CC1CCC2C(C1)OC(=O)CC3C(O2)CC(=O)N3",
        "cell_line": "U2OS",
        "dose_um": 1.0,
        "phenotype_tag": "actin",
    },
    {
        "broad_sample_id": "BRD-K81418486",
        "compound_name": "Cytochalasin D",
        "smiles": "CC1CCCC2C1C(=O)NC3(C2C(=CC=CC(C)C(C(C(=C)C(C(C=C3)O)OC(=O)C)C)O)O)CC4=CC=CC=C4",
        "cell_line": "U2OS",
        "dose_um": 1.0,
        "phenotype_tag": "actin",
    },
]


_PHENOTYPE_COLORS: dict[str, tuple[str, str, str]] = {
    # RGB tones for the Cell Painting "nucleus / mitochondria / actin" composite look.
    "control":              ("#1e3a8a", "#059669", "#f472b6"),
    "kinase-inhibitor":     ("#1e40af", "#16a34a", "#ec4899"),
    "microtubule":          ("#312e81", "#ca8a04", "#a855f7"),
    "DNA-damage":           ("#7f1d1d", "#15803d", "#be185d"),
    "translation-inhibitor":("#1e3a8a", "#047857", "#f472b6"),
    "mTOR-inhibitor":       ("#0f172a", "#65a30d", "#d946ef"),
    "HDAC-inhibitor":       ("#4c1d95", "#059669", "#ec4899"),
    "actin":                ("#1e3a8a", "#16a34a", "#f9a8d4"),
}


def phenotype_colors(tag: str) -> tuple[str, str, str]:
    return _PHENOTYPE_COLORS.get(tag, _PHENOTYPE_COLORS["control"])
