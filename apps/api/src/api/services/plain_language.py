"""Plain-language (patient-facing) translator.

Given an AnalysisResult's inputs (drug_id, target_gene, pgx_verdicts, pocket
observations, severity), generate a jargon-free description of:
  - what the 3D view is showing
  - how the drug works (with a physical analogy)
  - what the patient's genetics mean for them personally
  - what they should do next (always: talk to a doctor)

Also returns a compact glossary so on-screen jargon can be explained in hover
tooltips or an expandable panel.

Design rules:
  - No Greek letters, no -ases/-mers if avoidable.
  - Use lock-and-key / key-fits-slot analogies, not biochemistry.
  - Every recommendation points back to "talk to your oncologist".
  - Never assert a clinical outcome — always "may", "often", "can".
"""

from __future__ import annotations

from api.models import GlossaryTerm, HowWeKnow, PGxVerdict, PlainLanguage, PocketResidue
from api.services.bc_catalog import DRUGS, GENES


# --- Drug-specific analogies (1-2 sentences, lay-person friendly) ---------
DRUG_ANALOGIES: dict[str, str] = {
    "tamoxifen": (
        "Tamoxifen doesn't do anything on its own. It's a 'prodrug'. Your "
        "liver converts it into the active form (called endoxifen) using an "
        "enzyme called CYP2D6. The active form then slides into a slot on "
        "the estrogen receptor, blocking the estrogen signal that tells "
        "hormone-sensitive breast cancer cells to grow."
    ),
    "fulvestrant": (
        "Fulvestrant slots into the estrogen receptor the way estrogen "
        "itself would, but instead of turning the receptor on, it marks it "
        "for disposal. Your cells then destroy the receptor, so estrogen "
        "has nothing to attach to."
    ),
    "trastuzumab": (
        "Trastuzumab is an antibody, a targeted protein your immune "
        "system normally makes. This one grabs onto HER2, a protein that "
        "sits on the outside of some breast cancer cells and tells them to "
        "keep dividing. With trastuzumab attached, that 'divide!' signal "
        "is blocked and your immune system recognizes the cell as a target."
    ),
    "palbociclib": (
        "Palbociclib blocks the cell's internal clock, specifically two "
        "proteins called CDK4 and CDK6 that tell cells 'it's time to "
        "divide.' With the clock stopped, cancer cells can't progress "
        "through the cycle that lets them multiply."
    ),
    "olaparib": (
        "Olaparib jams an enzyme called PARP that helps cells repair "
        "damaged DNA. Most cells can use a backup repair system (the "
        "BRCA pathway). But cancer cells with a broken BRCA1 or BRCA2 "
        "gene don't have that backup, so when olaparib blocks PARP, "
        "those cells die from unrepaired DNA damage while healthy cells "
        "survive."
    ),
    "alpelisib": (
        "Alpelisib targets a growth-signal enzyme called PI3K-alpha. In "
        "tumors with a PIK3CA mutation, this enzyme is stuck in the 'on' "
        "position, constantly telling the cell to grow. Alpelisib turns "
        "that switch back off."
    ),
    "letrozole": (
        "Letrozole blocks aromatase, the enzyme that makes estrogen in "
        "postmenopausal women. Less estrogen in the body means less fuel "
        "for hormone-sensitive breast cancer cells."
    ),
    "capecitabine": (
        "Capecitabine is a pill that your body converts into a cancer-"
        "killing chemical called 5-FU. 5-FU sticks to an enzyme called "
        "thymidylate synthase (TYMS) that cancer cells need to build "
        "DNA. Without that enzyme working, rapidly-dividing cancer cells "
        "can't make new DNA and they die."
    ),
    "imatinib": (
        "Imatinib slots into a specific pocket on an overactive enzyme "
        "called BCR-ABL1, the one that drives chronic myeloid leukemia. "
        "Like a plug that blocks an electrical outlet, imatinib stops "
        "the enzyme from sending the 'keep growing' signal to leukemia "
        "cells."
    ),
}


DRUG_FORM: dict[str, str] = {
    "tamoxifen": "a daily pill",
    "fulvestrant": "a monthly injection",
    "trastuzumab": "an IV infusion",
    "palbociclib": "a daily pill",
    "olaparib": "a twice-daily pill",
    "alpelisib": "a daily pill",
    "letrozole": "a daily pill",
    "capecitabine": "an oral pill (prodrug for 5-FU)",
    "imatinib": "a daily pill",
}


# --- Plain-language verdict translations -----------------------------------
# Keyed by headline severity. Each returns a patient-facing sentence that
# doesn't over-promise or under-warn.
SEVERITY_PATIENT_SUMMARIES: dict[str, str] = {
    "benefit": (
        "Good news: based on the variants you entered, there's no obvious "
        "genetic reason this drug wouldn't work as expected. Your doctor can "
        "follow the standard dosing guidelines and monitor for the usual "
        "possible side effects."
    ),
    "info": (
        "Your variants don't match any major pharmacogenomic guideline "
        "for this drug. The 3D view is informational: it shows where "
        "your variant sits on the protein, but no specific dose change is "
        "indicated from genetics alone."
    ),
    "caution": (
        "Heads-up: your genetic profile may affect how well this drug "
        "works for you or how your body handles it. It doesn't mean the "
        "drug can't be used. It means the dose or the choice of drug "
        "may need adjustment. Your doctor should see this."
    ),
    "warning": (
        "One or more of your variants sits right where the drug binds. "
        "That makes it physically harder for the drug to do its job. This "
        "is a structural hint from the 3D model, not a clinical test, "
        "but it's worth raising with your oncologist."
    ),
    "contraindicated": (
        "Important: the combination of this drug and your genetic variant "
        "is known to carry a serious safety risk. Published guidelines "
        "recommend avoiding this drug or starting at a much lower dose. "
        "Please do not make treatment decisions from this app. Share "
        "this result with your oncologist."
    ),
}


# --- Glossary: jargon → plain English --------------------------------------
GLOSSARY_SOURCE: dict[str, str] = {
    "protein": (
        "A microscopic machine your body builds from instructions in your "
        "DNA. Most drugs work by sticking to a specific protein."
    ),
    "kinase": (
        "A type of protein that turns other proteins on or off by tagging "
        "them. Many cancer drugs work by blocking a specific kinase."
    ),
    "receptor": (
        "A 'catcher' protein on or inside a cell. Hormones and signals "
        "slot into receptors to tell the cell what to do."
    ),
    "enzyme": (
        "A protein that makes a specific chemical reaction happen, like "
        "a tool that cuts, joins, or converts other molecules."
    ),
    "gene": (
        "A section of your DNA that acts as the recipe for one protein. "
        "We all have two copies of most genes, one from each parent."
    ),
    "variant": (
        "A small change in the letters of your DNA. Some variants change "
        "how a protein works; many don't."
    ),
    "wild-type": (
        "The 'reference' version of a gene, what most people have. "
        "Wild-type means no variant was detected."
    ),
    "homozygous": (
        "Both of your two copies of a gene have the same variant."
    ),
    "heterozygous": (
        "One copy of the gene has the variant; the other copy is normal."
    ),
    "poor metabolizer": (
        "Your body breaks down (or activates) this drug much more slowly "
        "than average, because of your genetics."
    ),
    "intermediate metabolizer": (
        "Your body breaks down this drug somewhat more slowly than average."
    ),
    "binding pocket": (
        "A specific 'slot' on a protein, shaped like a keyhole, that "
        "a drug or natural molecule fits into."
    ),
    "prodrug": (
        "A medicine that has to be converted by your body (usually by your "
        "liver) into its active form before it does anything."
    ),
    "CPIC": (
        "A group of scientists that publishes official guidelines for when "
        "and how genetic results should change prescribing."
    ),
    "FDA label": (
        "The official prescribing information approved by the U.S. Food "
        "and Drug Administration."
    ),
    "pharmacogenomic": (
        "A fancy word for 'how your genes affect how a drug works for you.'"
    ),
}


def build_plain_language(
    drug_id: str,
    target_gene: str,
    target_uniprot: str,
    pgx_verdicts: list[PGxVerdict],
    pocket_residues: list[PocketResidue],
    headline_severity: str,
    has_pose: bool,
) -> PlainLanguage:
    drug = DRUGS.get(drug_id)
    drug_name = drug["name"] if drug else drug_id.title()
    gene = GENES.get(target_gene)
    gene_name = gene["name"] if gene else target_gene
    form = DRUG_FORM.get(drug_id, "a prescription medicine")

    in_pocket = [r for r in pocket_residues if r.in_pocket]

    # --- what_you_see -----------------------------------------------------
    what_you_see = (
        f"You're looking at a 3D model of {gene_name}, the protein {drug_name} "
        f"is designed to attach to. "
    )
    if has_pose:
        what_you_see += (
            f"The small bright shape is {drug_name}, positioned where it would "
            f"slot onto the protein. "
        )
    if in_pocket:
        pos_list = ", ".join(str(r.position) for r in in_pocket[:3])
        what_you_see += (
            f"The highlighted residues (position{'s' if len(in_pocket) > 1 else ''} "
            f"{pos_list}) are the spots in your DNA that differ from the reference, "
            f"and they sit inside the drug's binding slot, which can change how "
            f"well the drug fits."
        )
    elif pocket_residues:
        what_you_see += (
            "Your variants are shown on the protein but they sit away from the "
            "drug's binding slot, so the drug should still fit normally."
        )
    else:
        what_you_see += (
            "No variants in this target protein were entered, so you're seeing "
            "the standard (reference) shape of the protein with the drug docked."
        )

    # --- how_the_drug_works ----------------------------------------------
    analogy = DRUG_ANALOGIES.get(
        drug_id,
        f"{drug_name} binds to {gene_name} to change how it works in your cells.",
    )
    how_the_drug_works = f"{drug_name} is {form}. {analogy}"

    # --- what_it_means_for_you -------------------------------------------
    base_summary = SEVERITY_PATIENT_SUMMARIES.get(
        headline_severity,
        SEVERITY_PATIENT_SUMMARIES["info"],
    )
    what_it_means = base_summary
    # Attach the strongest applicable verdict's recommendation, translated.
    if pgx_verdicts:
        top = _pick_top_verdict(pgx_verdicts, headline_severity)
        translated = _translate_recommendation(top)
        what_it_means += f" Specifically: {translated}"

    # --- next_steps --------------------------------------------------------
    next_steps = (
        "This is an educational tool, not a medical test. Share this page "
        "with your oncologist and your pharmacist. If you haven't had formal "
        "pharmacogenomic testing done through a certified (CLIA) lab, they "
        "can order it, and any treatment decisions should be made together "
        "with them, not from this app."
    )

    # --- questions to ask the doctor --------------------------------------
    questions = _questions_for(drug_id, headline_severity, pgx_verdicts)

    # --- source provenance for "How we know this" -------------------------
    how_we_know = _how_we_know(pgx_verdicts)

    # --- glossary ---------------------------------------------------------
    terms = _pick_glossary_terms(drug_id, target_gene, pgx_verdicts, bool(in_pocket))

    return PlainLanguage(
        what_you_see=what_you_see,
        how_the_drug_works=how_the_drug_works,
        what_it_means_for_you=what_it_means,
        next_steps=next_steps,
        questions_to_ask=questions,
        how_we_know=how_we_know,
        glossary=[GlossaryTerm(term=t, definition=GLOSSARY_SOURCE[t]) for t in terms],
    )


def _pick_top_verdict(verdicts: list[PGxVerdict], severity: str) -> PGxVerdict:
    """Return the verdict that best matches the headline severity."""
    if severity == "contraindicated":
        for v in verdicts:
            if "avoid" in v.recommendation.lower():
                return v
    if severity == "benefit":
        for v in verdicts:
            if "approved" in v.recommendation.lower() or "eligible" in v.recommendation.lower():
                return v
    return verdicts[0]


def _translate_recommendation(v: PGxVerdict) -> str:
    """Rewrite a CPIC/FDA recommendation in patient-friendly language."""
    low = v.recommendation.lower()
    phenotype = v.phenotype.lower()

    if "avoid" in low and "fluoropyrimidine" in low:
        return (
            "the guidelines say this drug should generally be avoided for "
            "people with your variant because it can cause severe, sometimes "
            "life-threatening side effects. A different chemotherapy is "
            "usually chosen instead."
        )
    if "reduce" in low and "50" in low:
        return (
            "the guidelines say doctors should start at roughly half the "
            "usual dose and carefully watch how you respond, then adjust up "
            "if you tolerate it well."
        )
    if "alternative hormonal therapy" in low or "alternative endocrine" in low:
        return (
            "the guidelines suggest your doctor may consider a different "
            "kind of hormone-blocking medicine instead. Tamoxifen depends "
            "on your CYP2D6 enzyme, which isn't working efficiently for you."
        )
    if "higher" in low and "dose" in low:
        return (
            "the guidelines note that a slightly higher dose may help, or "
            "a different hormone-blocking medicine may be considered."
        )
    if "fda-approved" in low or "eligible" in low:
        return (
            "your variant actually makes you eligible for this targeted "
            "therapy. It's specifically indicated for patients with your "
            "genetic profile."
        )
    if "resistance" in phenotype:
        return (
            "your variant is associated with reduced response to this drug "
            "in prior studies, but it doesn't rule the drug out. Newer "
            "agents targeting your specific mutation may also be options."
        )
    # Generic fallback
    return (
        f"the published guidance for your profile ({v.phenotype}) is: "
        f"{v.recommendation}"
    )


def _questions_for(
    drug_id: str,
    severity: str,
    verdicts: list[PGxVerdict],
) -> list[str]:
    """Questions a patient could bring to their oncology appointment."""
    drug = DRUGS.get(drug_id)
    drug_name = drug["name"] if drug else drug_id.title()

    generic: list[str] = [
        f"How will we track whether {drug_name} is actually working for me?",
        f"What side effects should I watch for at home, and when should I call you?",
    ]

    by_severity: dict[str, list[str]] = {
        "benefit": [
            f"How long until we'd know if {drug_name} is effective?",
            "Are there foods, supplements, or other medications I should avoid while on this drug?",
        ],
        "info": [
            "Given my genetic profile, is there anything worth monitoring more closely?",
            "Should my family members consider pharmacogenomic testing?",
        ],
        "caution": [
            "Given my pharmacogenomic result, would you recommend staying on this drug or considering an alternative?",
            "Can you monitor whether the drug is working effectively for me? A blood test, imaging, anything else?",
            "What are the pros and cons of switching to a different medication in this class?",
            "Are there other drugs I'm taking that could further affect this one?",
        ],
        "warning": [
            "How does my variant affect your choice of drug or dose?",
            "Is there a different drug in the same class that would be a better fit for my biology?",
            "If we stay on this drug, what should we monitor and how often?",
        ],
        "contraindicated": [
            "Given the published safety guidance, what alternative treatment would you recommend?",
            "If we do proceed with this drug, what dose and monitoring plan do you propose?",
            "Is there any additional genetic testing you'd want before making a decision?",
            "Should my first-degree relatives be tested for this variant?",
        ],
    }

    drug_specific: dict[str, list[str]] = {
        "tamoxifen": [
            "Are there medications I'm already taking (like some antidepressants) that slow CYP2D6 down further?",
        ],
        "capecitabine": [
            "What's the starting dose you're recommending given my DPYD status?",
            "Will we adjust the dose over time based on how I respond?",
        ],
        "olaparib": [
            "Does my BRCA status change my prognosis or my family's screening recommendations?",
        ],
        "imatinib": [
            "How often will we do BCR-ABL monitoring blood tests?",
        ],
    }

    seen: set[str] = set()
    out: list[str] = []
    # Drug-specific questions lead — otherwise the 5-item cap pushes them off.
    for q in drug_specific.get(drug_id, []) + by_severity.get(severity, []) + generic:
        if q not in seen:
            seen.add(q)
            out.append(q)
    # Cap to avoid overwhelming the patient with too long a list.
    return out[:5]


def _how_we_know(verdicts: list[PGxVerdict]) -> HowWeKnow:
    """Attach a citation panel. Prefers CPIC over FDA over a generic ClinPGx link."""
    if verdicts:
        src = verdicts[0].source
        if "CPIC" in src:
            return HowWeKnow(
                source=src,
                link="https://cpicpgx.org/",
                summary=(
                    "The Clinical Pharmacogenetics Implementation Consortium (CPIC) "
                    "publishes evidence-graded guidelines on how genetic variants "
                    "should change drug prescribing. Guidelines are written by "
                    "expert panels and reviewed continuously as new evidence emerges."
                ),
            )
        if "FDA" in src:
            return HowWeKnow(
                source=src,
                link="https://www.fda.gov/medical-devices/precision-medicine/table-pharmacogenetic-associations",
                summary=(
                    "The FDA Table of Pharmacogenetic Associations lists gene-drug "
                    "pairs for which there is evidence that genetic variation affects "
                    "response, dosing, or safety, and which appear in the official "
                    "prescribing information (drug label)."
                ),
            )
        return HowWeKnow(
            source=src,
            link="https://www.clinpgx.org/",
            summary=(
                "Evidence summarized from the ClinPGx knowledge base (PharmGKB, "
                "CPIC, PharmVar), the canonical public pharmacogenomic reference."
            ),
        )
    return HowWeKnow(
        source="ClinPGx / CPIC reference",
        link="https://www.clinpgx.org/",
        summary=(
            "ClinPGx is the umbrella for PharmGKB and CPIC, the public knowledge "
            "base of drug-gene interactions, maintained by pharmacogenomic experts "
            "and updated as new evidence emerges."
        ),
    )


def _pick_glossary_terms(
    drug_id: str,
    target_gene: str,
    verdicts: list[PGxVerdict],
    has_pocket_hit: bool,
) -> list[str]:
    """Pick only the terms that actually appear for this result, so the
    glossary is useful rather than overwhelming."""
    picks: list[str] = ["gene", "variant", "protein"]
    gene_upper = target_gene.upper()
    if gene_upper in {"ABL1", "ERBB2", "CDK4"}:
        picks.append("kinase")
    if gene_upper in {"ESR1"}:
        picks.append("receptor")
    if gene_upper in {"CYP2D6", "DPYD", "CYP19A1", "TYMS"}:
        picks.append("enzyme")
    if drug_id == "tamoxifen" or drug_id == "capecitabine":
        picks.append("prodrug")
    if has_pocket_hit:
        picks.append("binding pocket")
    # Zygosity terms when relevant.
    zygosities = {v.zygosity for v in verdicts}
    if "homozygous" in zygosities:
        picks.append("homozygous")
    if "heterozygous" in zygosities:
        picks.append("heterozygous")
    # Metabolizer terms when relevant.
    phenotypes = {v.phenotype.lower() for v in verdicts}
    if any("poor metabolizer" in p for p in phenotypes):
        picks.append("poor metabolizer")
    if any("intermediate" in p for p in phenotypes):
        picks.append("intermediate metabolizer")
    if not verdicts:
        picks.append("wild-type")
    # Source concepts.
    sources = " ".join(v.source.lower() for v in verdicts)
    if "cpic" in sources:
        picks.append("CPIC")
    if "fda" in sources:
        picks.append("FDA label")
    picks.append("pharmacogenomic")
    # De-duplicate preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for p in picks:
        if p in GLOSSARY_SOURCE and p not in seen:
            seen.add(p)
            out.append(p)
    return out
