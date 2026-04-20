"""Variant-analysis orchestrator.

Takes a drug_id + list of VariantInput records and produces a single
AnalysisResult combining:
  - matching CPIC/FDA pharmacogenomic guidance (from bc_catalog)
  - structural pocket-proximity analysis of the user's variants on the drug's
    primary target (AlphaFold structure + docked ligand)
  - a high-level "headline" verdict for the UI

Never makes treatment recommendations of its own — only surfaces the evidence
attached to each matching rule. Anything not covered by a rule is reported as
"structural observation only, not a clinical recommendation".
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from api.models import (
    AnalysisResult,
    PGxVerdict,
    PocketResidue,
    VariantInput,
)
from api.services import alphafold, docking, pocket, storage, variants
from api.services.bc_catalog import (
    DRUGS,
    GENES,
    VARIANTS,
    PGxRule,
    rules_for_drug,
)

logger = logging.getLogger(__name__)


DISCLAIMERS = [
    "Educational use only. This tool does NOT make medical or treatment recommendations.",
    "Pharmacogenomic guidance shown is summarized from public CPIC/FDA sources; "
    "always confirm with a qualified clinician and a CLIA-certified genetic test.",
    "Structural pocket analysis is a heuristic — residues close to the ligand "
    "in a docked model are more likely to affect binding, but this is not a "
    "binding-affinity calculation.",
    "Do not make treatment decisions based on this app. Consult an oncologist "
    "and a clinical pharmacogenomicist.",
]


class AnalysisError(ValueError):
    pass


async def run_analysis(
    drug_id: str,
    variant_inputs: list[VariantInput],
) -> AnalysisResult:
    drug = DRUGS.get(drug_id)
    if drug is None:
        raise AnalysisError(f"unknown drug id {drug_id!r}")

    target_gene = drug["primary_target_gene"]
    gene_entry = GENES.get(target_gene)
    if gene_entry is None:
        raise AnalysisError(
            f"drug {drug_id!r} targets gene {target_gene!r} which is not in the curated gene list"
        )

    # --- 1) Resolve input variants into (gene, positions, catalog_ids) ---
    resolved = await _resolve_variants(variant_inputs)

    # --- 2) Match pharmacogenomic rules ---
    pgx_verdicts = _match_rules(drug_id, resolved)

    # --- 3) Structural analysis on the drug's primary target ---
    # Only residues whose gene matches the target gene can be mapped on this structure.
    target_positions = [
        (r["position"], r.get("gene_symbol"))
        for r in resolved
        if r.get("gene_symbol") == target_gene
    ]

    protein_pdb_bytes, protein_url = await alphafold.fetch_structure(gene_entry["uniprot_id"])
    pose_url: str | None = None
    pocket_residues: list[PocketResidue] = []

    pose_pdb_text: str | None = None
    if drug["smiles"]:
        # Reuse the docking service (RDKit stub or Modal DiffDock depending on flag).
        poses = await docking.dock(protein_pdb_bytes, drug["smiles"])
        if poses:
            top = poses[0]
            pose_key = f"analysis/{uuid4().hex}/pose.pdb"
            pose_url = await storage.put(
                pose_key, top.pose_pdb.encode("utf-8"), "chemical/x-pdb"
            )
            pose_pdb_text = top.pose_pdb

    # Residue distances: prefer measuring against the docked pose (has ligand);
    # if no docking was performed (e.g. antibody drug), report positions without pocket flags.
    if pose_pdb_text and target_positions:
        positions_only = [p for p, _ in target_positions]
        distances = pocket.compute_distances(pose_pdb_text, positions_only)
        dist_by_pos = {d.position: d for d in distances}
        for pos, _gene in target_positions:
            d = dist_by_pos.get(pos)
            if d is None:
                continue
            in_pocket = d.min_distance != float("inf") and d.min_distance <= pocket.POCKET_RADIUS_ANGSTROM
            pocket_residues.append(
                PocketResidue(
                    position=pos,
                    wildtype_aa=d.wildtype_aa,
                    variant_aa=None,
                    min_distance_to_ligand_angstrom=(
                        None if d.min_distance == float("inf") else round(d.min_distance, 2)
                    ),
                    in_pocket=in_pocket,
                )
            )
    elif target_positions:
        for pos, _ in target_positions:
            pocket_residues.append(
                PocketResidue(
                    position=pos,
                    wildtype_aa=None,
                    variant_aa=None,
                    min_distance_to_ligand_angstrom=None,
                    in_pocket=False,
                )
            )

    # --- 4) Headline ---
    headline, severity = _headline(drug["name"], pgx_verdicts, pocket_residues)

    return AnalysisResult(
        id=uuid4().hex,
        drug_id=drug["id"],
        drug_name=drug["name"],
        target_gene=target_gene,
        target_uniprot=gene_entry["uniprot_id"],
        protein_pdb_url=protein_url,
        pose_pdb_url=pose_url,
        pgx_verdicts=pgx_verdicts,
        pocket_residues=pocket_residues,
        headline=headline,
        headline_severity=severity,
        disclaimers=DISCLAIMERS,
        created_at=datetime.utcnow(),
    )


async def _resolve_variants(
    variant_inputs: list[VariantInput],
) -> list[dict]:
    """Flatten user variants into {gene_symbol, position, catalog_id?, zygosity}.

    Returns a list of dicts so the rules matcher + pocket analysis can share
    the same structure.
    """
    out: list[dict] = []
    for v in variant_inputs:
        if v.catalog_id:
            entry = VARIANTS.get(v.catalog_id)
            if entry is None:
                raise AnalysisError(f"unknown variant catalog id {v.catalog_id!r}")
            for pos in (entry["residue_positions"] or [0]):
                out.append({
                    "gene_symbol": entry["gene_symbol"],
                    "position": pos,
                    "catalog_id": entry["id"],
                    "zygosity": v.zygosity,
                    "label": entry["name"],
                })
            if not entry["residue_positions"]:
                # Splice/metabolism variants without residue positions still
                # need to flow through for PGx-rule matching.
                out.append({
                    "gene_symbol": entry["gene_symbol"],
                    "position": 0,
                    "catalog_id": entry["id"],
                    "zygosity": v.zygosity,
                    "label": entry["name"],
                })
        elif v.gene_symbol and v.protein_sequence:
            uniprot = variants.gene_for_symbol(v.gene_symbol)
            wildtype = await variants.fetch_uniprot_sequence(uniprot)
            subs, has_indel = variants.align_and_diff(wildtype, v.protein_sequence)
            for pos, wt, alt in subs:
                out.append({
                    "gene_symbol": v.gene_symbol,
                    "position": pos,
                    "catalog_id": None,
                    "zygosity": v.zygosity,
                    "label": f"{v.gene_symbol} p.{wt}{pos}{alt}",
                })
            if has_indel:
                logger.info("sequence for %s has an indel; positions skipped", v.gene_symbol)
        else:
            raise AnalysisError(
                "variant must have either catalog_id or (gene_symbol + protein_sequence)"
            )
    return out


def _match_rules(drug_id: str, resolved: list[dict]) -> list[PGxVerdict]:
    drug = DRUGS[drug_id]
    verdicts: list[PGxVerdict] = []
    rules = rules_for_drug(drug_id)
    seen_keys: set[tuple[str, str, str]] = set()
    for r in resolved:
        cid = r.get("catalog_id")
        if not cid:
            continue
        for rule in rules:
            if cid not in rule["variant_ids"]:
                continue
            if rule["genotype"] != "any" and rule["genotype"] != r["zygosity"]:
                continue
            key = (cid, rule["phenotype"], rule["recommendation"][:40])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            verdicts.append(_rule_to_verdict(drug["name"], rule, r))
    return verdicts


def _rule_to_verdict(drug_name: str, rule: PGxRule, resolved: dict) -> PGxVerdict:
    return PGxVerdict(
        drug_name=drug_name,
        gene_symbol=rule["gene_symbol"],
        variant_label=resolved["label"],
        zygosity=resolved["zygosity"],
        phenotype=rule["phenotype"],
        recommendation=rule["recommendation"],
        evidence_level=rule["evidence_level"],
        source=rule["source"],
    )


def _headline(
    drug_name: str,
    verdicts: list[PGxVerdict],
    pocket_residues: list[PocketResidue],
) -> tuple[str, str]:
    in_pocket_count = sum(1 for p in pocket_residues if p.in_pocket)

    if verdicts:
        # Highest-severity rule wins the headline.
        contraindications = [
            v for v in verdicts if "avoid" in v.recommendation.lower()
        ]
        benefits = [
            v for v in verdicts
            if "approved" in v.recommendation.lower()
            or "eligible" in v.recommendation.lower()
            or "eligibility" in v.recommendation.lower()
        ]
        if contraindications:
            return (
                f"{drug_name}: avoid — {contraindications[0].phenotype} "
                f"({contraindications[0].variant_label}).",
                "contraindicated",
            )
        if benefits:
            return (
                f"{drug_name}: your variant matches an FDA-approved biomarker "
                f"for this therapy.",
                "benefit",
            )
        return (
            f"{drug_name}: dosing or choice may need adjustment — "
            f"{verdicts[0].phenotype}.",
            "caution",
        )

    if in_pocket_count > 0:
        return (
            f"{drug_name}: {in_pocket_count} of your variant residue(s) sit "
            f"inside the binding pocket — structural disruption likely.",
            "warning",
        )
    if pocket_residues:
        return (
            f"{drug_name}: your variants are on the target but outside the "
            f"binding pocket — binding likely preserved.",
            "info",
        )
    return (
        f"{drug_name}: no matching PGx rule for your variants. Structural "
        f"view only.",
        "info",
    )
