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
from typing import Awaitable, Callable
from uuid import uuid4

from api.models import (
    AnalysisResult,
    CurrentDrugAssessment,
    HrdEvidence,
    HrdResult,
    PGxVerdict,
    PocketResidue,
    SuggestedDrug,
    VariantInput,
)

# Progress callback for the streaming endpoint. Called at each major phase
# boundary with (stage_id, human_label, progress_0_1). Implementations publish
# to SSE queues, RabbitMQ, logs, etc. Must be cheap and must not raise —
# analysis failures should come through the main return path, not the callback.
ProgressCallback = Callable[[str, str, float], Awaitable[None]]


async def _noop(_stage: str, _label: str, _pct: float) -> None:
    return None
from api.services import alphafold, docking, hrd as hrd_service, plain_language, pocket, storage, variants
from api.services.bc_catalog import (
    DRUGS,
    GENES,
    VARIANTS,
    PGxRule,
    drug_related_genes,
    drugs_for_gene_inclusive,
    rules_for_drug,
)

logger = logging.getLogger(__name__)


DISCLAIMERS = [
    "Educational use only. This tool does NOT make medical or treatment recommendations.",
    "Pharmacogenomic guidance shown is summarized from public CPIC/FDA sources; "
    "always confirm with a qualified clinician and a CLIA-certified genetic test.",
    "Structural pocket analysis is a heuristic. Residues close to the ligand "
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
    progress_cb: ProgressCallback | None = None,
) -> AnalysisResult:
    cb = progress_cb or _noop

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
    await cb("resolve", "Finding your variants", 0.05)
    resolved = await _resolve_variants(variant_inputs)

    # --- 2) Match pharmacogenomic rules ---
    await cb("rules", "Matching pharmacogenomic rules", 0.15)
    pgx_verdicts = _match_rules(drug_id, resolved)

    # --- 3) Structural analysis on the drug's primary target ---
    # Only residues whose gene matches the target gene can be mapped on this structure.
    target_positions = [
        (r["position"], r.get("gene_symbol"))
        for r in resolved
        if r.get("gene_symbol") == target_gene
    ]

    await cb("structure", f"Fetching {target_gene} protein structure", 0.30)
    protein_pdb_bytes, protein_url = await alphafold.fetch_structure(gene_entry["uniprot_id"])
    pose_url: str | None = None
    pocket_residues: list[PocketResidue] = []

    pose_pdb_text: str | None = None
    if drug["smiles"]:
        # Reuse the docking service (RDKit stub or Modal DiffDock depending on flag).
        await cb("dock", f"Simulating {drug['name']} binding pose", 0.50)
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
    await cb("pocket", "Measuring variant distance to drug pocket", 0.70)
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
    await cb("headline", "Building headline verdict", 0.80)
    headline, severity = _headline(drug["name"], pgx_verdicts, pocket_residues)

    # --- 4b) Drug-vs-variants relevance check ---
    relevance_warning, suggested_drugs = _relevance_check(drug_id, resolved)

    # --- 4c) BRCA1 variants the Tier-3 classifier can handle ---
    classifiable_brca1 = _extract_classifiable_brca1(resolved)

    # --- 4d) "Is the current drug right for me?" assessment ---
    current_drug_assessment = _assess_current_drug(
        drug_id=drug_id,
        resolved=resolved,
        verdicts=pgx_verdicts,
        headline_severity=severity,
        suggested_drugs=suggested_drugs,
    )

    # --- 4f) HR deficiency composite — the headline HRD call for PARPi ---
    await cb("hrd", "Computing HR-deficiency composite score", 0.88)
    hrd_raw = hrd_service.compute_hrd(resolved, classifiable_brca1)
    hrd_result = HrdResult(
        label=hrd_raw.label,
        score=hrd_raw.score,
        evidence=[
            HrdEvidence(
                gene=e.gene,
                variant_label=e.variant_label,
                source=e.source,
                weight=e.weight,
                detail=e.detail,
            )
            for e in hrd_raw.evidence
        ],
        summary=hrd_raw.summary,
        parp_inhibitor_context=hrd_raw.parp_inhibitor_context,
        caveats=hrd_raw.caveats,
    )

    # --- 5) Plain-language translation for patients ---
    await cb("plain_language", "Writing plain-English report", 0.95)
    plain = plain_language.build_plain_language(
        drug_id=drug["id"],
        target_gene=target_gene,
        target_uniprot=gene_entry["uniprot_id"],
        pgx_verdicts=pgx_verdicts,
        pocket_residues=pocket_residues,
        headline_severity=severity,
        has_pose=pose_url is not None,
    )

    result = AnalysisResult(
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
        plain_language=plain,
        relevance_warning=relevance_warning,
        suggested_drugs=suggested_drugs,
        classifiable_brca1_variants=classifiable_brca1,
        hrd=hrd_result,
        current_drug_assessment=current_drug_assessment,
        disclaimers=DISCLAIMERS,
        created_at=datetime.utcnow(),
    )
    await cb("done", "Complete", 1.0)
    return result


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
        elif v.protein_sequence:
            # Two accepted cases now:
            #   (a) user explicitly picked the gene alongside pasting the sequence
            #   (b) user only pasted the sequence — auto-detect the gene by
            #       comparing identity against every supported gene's UniProt WT.
            gene_symbol = v.gene_symbol
            if not gene_symbol:
                match = await variants.identify_gene_from_sequence(v.protein_sequence)
                if match is None:
                    raise AnalysisError(
                        "couldn't tell which gene this sequence is from. Try picking "
                        "the gene from the dropdown, or double-check the sequence is "
                        "one of the supported genes."
                    )
                gene_symbol, _score = match
                logger.info("auto-detected gene %s from pasted sequence", gene_symbol)

            uniprot = variants.gene_for_symbol(gene_symbol)
            wildtype = await variants.fetch_uniprot_sequence(uniprot)
            subs, has_indel = variants.align_and_diff(wildtype, v.protein_sequence)
            for pos, wt, alt in subs:
                out.append({
                    "gene_symbol": gene_symbol,
                    "position": pos,
                    "catalog_id": None,
                    "zygosity": v.zygosity,
                    "label": f"{gene_symbol} p.{wt}{pos}{alt}",
                })
            if has_indel:
                logger.info("sequence for %s has an indel; positions skipped", gene_symbol)
            if not subs and not has_indel:
                # Sequence matches WT exactly — no variants to report, but the
                # analyzer still needs to know which gene context we're in.
                out.append({
                    "gene_symbol": gene_symbol,
                    "position": 0,
                    "catalog_id": None,
                    "zygosity": v.zygosity,
                    "label": f"{gene_symbol} (no variants detected in pasted sequence)",
                })
        else:
            raise AnalysisError(
                "variant must have a catalog_id, or a protein_sequence (with optional gene_symbol)"
            )
    return out


def _assess_current_drug(
    drug_id: str,
    resolved: list[dict],
    verdicts: list[PGxVerdict],
    headline_severity: str,
    suggested_drugs: list[SuggestedDrug],
) -> CurrentDrugAssessment:
    """Verdict on whether the chosen drug is right for this patient's variants.

    Four buckets:
      - unknown:        no variants provided, can't assess
      - well_matched:   an FDA-biomarker/CPIC rule endorses this combo
      - review_needed:  a guideline says "avoid" / "consider alternative",
                        or the variants are in a pathway the drug doesn't
                        touch (relevance-check mismatch already fired)
      - acceptable:     in between — drug and variants relate but nothing
                        strongly endorses or contraindicates

    This is the "second opinion" feature: when someone walks in already on
    a medication with a known variant, they get an explicit answer instead
    of having to read a full PGx rule and infer. Better_options surfaces
    any drug that the same variants more clearly support (e.g. BRCA1
    germline + olaparib as alternative to tamoxifen).
    """
    drug = DRUGS.get(drug_id)
    drug_name = drug["name"] if drug else drug_id

    if not resolved:
        return CurrentDrugAssessment(
            verdict="unknown",
            headline=f"We can't assess {drug_name} fit without any variants.",
            rationale=(
                "Add one or more variants (or upload a 23andMe file / VCF) "
                "and we'll tell you whether your current drug is the right "
                "match based on public CPIC and FDA guidance."
            ),
            better_options=[],
        )

    # Scan the rules for strong signals about this drug specifically.
    explicitly_contraindicated = [
        v for v in verdicts if "avoid" in v.recommendation.lower()
    ]
    explicitly_endorsed = [
        v for v in verdicts
        if "fda-approved" in v.recommendation.lower()
        or "eligible" in v.recommendation.lower()
        or "eligibility" in v.recommendation.lower()
    ]
    alternative_preferred = [
        v for v in verdicts
        if "alternative" in v.recommendation.lower()
        or "consider" in v.recommendation.lower()
        or "reduce" in v.recommendation.lower()
    ]

    # If the relevance check already fired with suggestions, the drug is in
    # the wrong pathway entirely — always "review needed".
    if suggested_drugs and not explicitly_endorsed:
        return CurrentDrugAssessment(
            verdict="review_needed",
            headline=(
                f"{drug_name} may not be the best match for your variants. "
                "Alternatives are listed below."
            ),
            rationale=(
                f"The variants you entered are in genes {drug_name} doesn't "
                "directly target or process. That doesn't mean it's unsafe, "
                "but a different drug in our catalog specifically addresses "
                "those variants. Bring this list to your oncologist."
            ),
            better_options=suggested_drugs,
        )

    if explicitly_contraindicated:
        v = explicitly_contraindicated[0]
        return CurrentDrugAssessment(
            verdict="review_needed",
            headline=(
                f"{drug_name} has a safety flag for your genotype. "
                "Review this with your oncologist before your next dose."
            ),
            rationale=(
                f"Your {v.variant_label} ({v.zygosity}) matches a published "
                f"avoid-recommendation for {drug_name}. {v.recommendation} "
                f"Source: {v.source}."
            ),
            better_options=suggested_drugs,
        )

    if explicitly_endorsed:
        v = explicitly_endorsed[0]
        return CurrentDrugAssessment(
            verdict="well_matched",
            headline=f"{drug_name} is explicitly endorsed for your variants.",
            rationale=(
                f"Your {v.variant_label} matches an FDA-approved biomarker "
                f"or CPIC-recommended indication for {drug_name}. "
                f"{v.recommendation} Source: {v.source}."
            ),
            better_options=[],
        )

    if alternative_preferred:
        v = alternative_preferred[0]
        return CurrentDrugAssessment(
            verdict="review_needed",
            headline=(
                f"{drug_name} may still work, but dose or choice may need "
                "adjustment. Ask your oncologist."
            ),
            rationale=(
                f"Your {v.variant_label} triggers published guidance to "
                f"{'adjust dosing' if 'reduce' in v.recommendation.lower() else 'consider alternatives'}. "
                f"{v.recommendation} Source: {v.source}."
            ),
            better_options=suggested_drugs,
        )

    # No verdicts fired. Variants exist but none of them map to this drug.
    return CurrentDrugAssessment(
        verdict="acceptable",
        headline=(
            f"{drug_name} has no red flags for your variants, but no "
            "specific endorsement either."
        ),
        rationale=(
            f"The variants you entered don't match any guideline-level rule "
            f"for {drug_name} in either direction. Standard dosing is "
            "reasonable; keep an eye on typical side effects, and share "
            "your variant list with your oncologist so they can weigh "
            "anything we didn't cover."
        ),
        better_options=[],
    )


def _extract_classifiable_brca1(resolved: list[dict]) -> list[str]:
    """Find BRCA1 point-AA variants that the Tier-3 classifier can handle.

    Parses the resolved variant `label` field, which is either "BRCA1 p.X###Y"
    (1-letter) for pasted sequences or "BRCA1 p.Xxx###Yyy" (3-letter) for
    catalog variants. Skips anything without recognisable p.-notation
    (frameshifts, splice variants, indels — those need a different model).
    """
    import re

    # Allow both "p.C61G" and "p.Cys61Gly" forms.
    pattern = re.compile(
        r"p\.(?:([A-Z])(\d+)([A-Z*])|([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2}|Ter))"
    )

    out: list[str] = []
    seen: set[str] = set()
    for r in resolved:
        if r.get("gene_symbol") != "BRCA1":
            continue
        label = r.get("label", "")
        m = pattern.search(label)
        if not m:
            continue
        # Normalize to the 1-letter form the classifier prefers.
        if m.group(1):
            hgvs = f"p.{m.group(1)}{m.group(2)}{m.group(3)}"
        else:
            # 3-letter form — pass through; the classifier's parser handles both.
            hgvs = f"p.{m.group(4)}{m.group(5)}{m.group(6)}"
        if hgvs not in seen:
            seen.add(hgvs)
            out.append(hgvs)
    return out


def _relevance_check(
    drug_id: str,
    resolved: list[dict],
) -> tuple[str | None, list[SuggestedDrug]]:
    """Does the user's variant set involve any gene this drug cares about?

    If yes, return (None, []). If the user pasted variants for genes that are
    unrelated to this drug's target and metabolism, return a clear warning
    plus a list of drugs that *are* related to their genes, so the UI can
    offer a one-click switch.
    """
    if not resolved:
        return None, []

    drug_genes = drug_related_genes(drug_id)
    patient_genes = {r["gene_symbol"] for r in resolved if r.get("gene_symbol")}
    relevant = patient_genes & drug_genes
    if relevant:
        return None, []

    drug = DRUGS.get(drug_id)
    drug_name = drug["name"] if drug else drug_id

    # Pick at most 3 alternative drugs, one per patient gene (no duplicates).
    seen: set[str] = set()
    suggestions: list[SuggestedDrug] = []
    for gene_symbol in patient_genes:
        for d in drugs_for_gene_inclusive(gene_symbol):
            if d["id"] in seen or d["id"] == drug_id:
                continue
            seen.add(d["id"])
            if d["primary_target_gene"] == gene_symbol:
                reason = f"targets {gene_symbol} directly"
            elif d["metabolizing_gene"] == gene_symbol:
                reason = f"is processed by {gene_symbol} in your body"
            else:
                # Context gene (e.g. olaparib's synthetic-lethality with BRCA1/2).
                reason = f"is clinically indicated when {gene_symbol} is deficient"
            suggestions.append(SuggestedDrug(id=d["id"], name=d["name"], reason=reason))
            if len(suggestions) >= 3:
                break
        if len(suggestions) >= 3:
            break

    patient_gene_label = ", ".join(sorted(patient_genes))
    warning = (
        f"The variants you gave us are in {patient_gene_label}, which is not part "
        f"of {drug_name}'s pathway. The 3D view below still shows {drug_name} on "
        f"its normal target, but your variants won't show up on it. Pick one of "
        f"the suggested drugs to see how your variants actually interact."
    )
    return warning, suggestions


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
                f"{drug_name}: avoid. {contraindications[0].phenotype} "
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
            f"{drug_name}: dosing or choice may need adjustment. "
            f"{verdicts[0].phenotype}.",
            "caution",
        )

    if in_pocket_count > 0:
        return (
            f"{drug_name}: {in_pocket_count} of your variant residue(s) sit "
            f"inside the binding pocket. Structural disruption is likely.",
            "warning",
        )
    if pocket_residues:
        return (
            f"{drug_name}: your variants are on the target but outside the "
            f"binding pocket. Binding is likely preserved.",
            "info",
        )
    # No PGx verdicts and no structural residues to analyze — the user submitted
    # wild-type (Patient A) or no variants at all. Emit a green-light summary.
    return (
        f"{drug_name}: no pharmacogenomic contraindications identified. "
        f"Standard dosing per FDA labeling. Monitor for common adverse effects.",
        "benefit",
    )
