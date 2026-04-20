"""Cell Painting morphology retrieval.

v1 baseline: Morgan fingerprint (2048 bits, radius 2) + Tanimoto similarity
over a small bundled catalog (`catalog_data.CATALOG`). This is the fallback
path explicitly blessed by the spec: "use Morgan fingerprints on the query
side and retrieve by compound similarity to the JUMP catalog — this is a
legitimate baseline and gets you something demo-able fast."

v2: swap in a FAISS IndexFlatIP over real CellProfiler/DINO embeddings
produced by `scripts/build_faiss_index.py`.

Thumbnails are synthesized on the fly as SVG placeholders so the UX works
with zero external image downloads. The SVG encodes the compound name, cell
line, dose, and a phenotype-tinted Voronoi-ish cell mosaic.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
from dataclasses import dataclass

from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem

from api.models.morphology import MorphologyMatch
from api.services import storage
from api.services.catalog_data import CATALOG, CatalogEntry, phenotype_colors

_FP_RADIUS = 2
_FP_BITS = 2048


@dataclass(frozen=True)
class _CatalogFingerprint:
    entry: CatalogEntry
    fp: DataStructs.ExplicitBitVect


_catalog_fps_cache: list[_CatalogFingerprint] | None = None


def _morgan_fp(smiles: str) -> DataStructs.ExplicitBitVect | None:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return AllChem.GetMorganFingerprintAsBitVect(mol, _FP_RADIUS, nBits=_FP_BITS)


def _catalog_fingerprints() -> list[_CatalogFingerprint]:
    global _catalog_fps_cache
    if _catalog_fps_cache is None:
        out: list[_CatalogFingerprint] = []
        for entry in CATALOG:
            fp = _morgan_fp(entry["smiles"])
            if fp is None:
                continue
            out.append(_CatalogFingerprint(entry=entry, fp=fp))
        _catalog_fps_cache = out
    return _catalog_fps_cache


def _query_fp_hex(smiles: str) -> tuple[DataStructs.ExplicitBitVect, str]:
    fp = _morgan_fp(smiles)
    if fp is None:
        raise ValueError(f"invalid SMILES: {smiles!r}")
    on_bits = list(fp.GetOnBits())
    # Short stable hex for display (first 128 bits of SHA-256 of the bitstring).
    bitstr = "".join("1" if b in set(on_bits) else "0" for b in range(_FP_BITS))
    return fp, hashlib.sha256(bitstr.encode()).hexdigest()[:32]


async def query(smiles: str, k: int = 7) -> tuple[str, list[MorphologyMatch], str]:
    """Return (query_fp_hex, top-k matches, control_url).

    The DMSO control entry is always served as `control_url`; the top-k
    matches exclude it.
    """
    query_fp, fp_hex = _query_fp_hex(smiles)
    scored: list[tuple[float, _CatalogFingerprint]] = []
    for cfp in _catalog_fingerprints():
        sim = DataStructs.TanimotoSimilarity(query_fp, cfp.fp)
        scored.append((sim, cfp))
    scored.sort(key=lambda t: t[0], reverse=True)

    control_entry = next(
        (cfp.entry for _, cfp in scored if cfp.entry["compound_name"].startswith("DMSO")),
        CATALOG[0],
    )
    control_url = await _thumbnail(control_entry)

    matches: list[MorphologyMatch] = []
    rank = 1
    for sim, cfp in scored:
        if cfp.entry["compound_name"].startswith("DMSO"):
            continue
        url = await _thumbnail(cfp.entry)
        matches.append(
            MorphologyMatch(
                rank=rank,
                similarity=float(sim),
                compound_name=cfp.entry["compound_name"],
                broad_sample_id=cfp.entry["broad_sample_id"],
                image_url=url,
                channel_urls=None,
                cell_line=cfp.entry["cell_line"],
                perturbation_dose_um=cfp.entry["dose_um"],
            )
        )
        rank += 1
        if len(matches) >= k:
            break
    return fp_hex, matches, control_url


async def _thumbnail(entry: CatalogEntry) -> str:
    key = f"morphology/thumbnails/{entry['broad_sample_id']}.svg"
    if await storage.exists(key):
        return f"{(await storage.put(key, await _render_thumbnail(entry), 'image/svg+xml'))}"
    svg = await _render_thumbnail(entry)
    return await storage.put(key, svg, "image/svg+xml")


async def _render_thumbnail(entry: CatalogEntry) -> bytes:
    def render() -> bytes:
        return _render_svg(entry)
    return await asyncio.to_thread(render)


def _render_svg(entry: CatalogEntry) -> bytes:
    bg, org, actin = phenotype_colors(entry["phenotype_tag"])
    rng = random.Random(entry["broad_sample_id"])
    cells: list[str] = []
    for _ in range(18):
        cx = rng.uniform(10, 290)
        cy = rng.uniform(10, 190)
        rx = rng.uniform(14, 30)
        ry = rng.uniform(10, 24)
        rot = rng.uniform(0, 180)
        # Nucleus
        cells.append(
            f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx*0.45:.1f}" ry="{ry*0.45:.1f}" '
            f'fill="{bg}" fill-opacity="0.9" transform="rotate({rot:.1f} {cx:.1f} {cy:.1f})"/>'
        )
        # Cytoplasm / actin halo
        cells.append(
            f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
            f'fill="none" stroke="{actin}" stroke-opacity="0.55" stroke-width="1.2" '
            f'transform="rotate({rot:.1f} {cx:.1f} {cy:.1f})"/>'
        )
        # Mitochondria speckles
        for _ in range(3):
            mx = cx + rng.uniform(-rx * 0.6, rx * 0.6)
            my = cy + rng.uniform(-ry * 0.6, ry * 0.6)
            cells.append(
                f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="1.3" fill="{org}" fill-opacity="0.85"/>'
            )

    label_dose = f"{entry['dose_um']:g} µM" if entry["dose_um"] else "—"
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200" width="300" height="200">
  <defs>
    <radialGradient id="bg" cx="50%" cy="50%" r="75%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#020617"/>
    </radialGradient>
  </defs>
  <rect width="300" height="200" fill="url(#bg)"/>
  {''.join(cells)}
  <text x="10" y="188" font-family="ui-sans-serif,system-ui,sans-serif" font-size="10" fill="#e2e8f0" opacity="0.85">
    {entry['compound_name']} · {entry['cell_line']} · {label_dose}
  </text>
</svg>
"""
    return svg.encode("utf-8")
