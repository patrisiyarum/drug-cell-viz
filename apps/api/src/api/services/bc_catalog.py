"""Breast cancer drug + gene + variant catalog.

Source notes:
- Drug-gene pharmacogenomic guidance follows CPIC (Clinical Pharmacogenetics
  Implementation Consortium) and FDA PGx labeling. CPIC evidence levels:
    A = Strong (act on it), B = Moderate, C = Optional, D = Informative.
- Variant pathogenicity / clinical significance labels follow ACMG/ClinVar
  classifications (pathogenic, likely pathogenic, VUS, benign).
- This catalog is educational. It is NOT a substitute for medical genetics
  consultation or clinical pharmacogenomic testing.

This module is deliberately hand-curated and small. Expanding it is additive —
add entries below, no structural changes.
"""

from __future__ import annotations

from typing import Literal, TypedDict

DrugCategory = Literal[
    "hormone_therapy",
    "her2_targeted",
    "cdk46_inhibitor",
    "parp_inhibitor",
    "pi3k_inhibitor",
    "chemotherapy",
    "aromatase_inhibitor",
]


class GeneEntry(TypedDict):
    symbol: str
    name: str
    uniprot_id: str
    role: str  # what it does in breast cancer care


class DrugEntry(TypedDict):
    id: str
    name: str
    smiles: str
    category: DrugCategory
    primary_target_gene: str  # symbol from GENES
    metabolizing_gene: str | None  # gene whose variants affect metabolism
    mechanism: str
    breast_cancer_indication: str


class VariantEntry(TypedDict):
    id: str  # stable id we make up
    gene_symbol: str
    name: str  # display name, e.g. "BRCA1 c.68_69del" or "CYP2D6*4"
    hgvs_protein: str | None  # e.g. "p.Glu23ValfsTer17" or "p.Y537S"
    residue_positions: list[int]  # 1-indexed, empty for regulatory/intronic
    clinical_significance: Literal[
        "pathogenic",
        "likely_pathogenic",
        "uncertain",
        "likely_benign",
        "benign",
        "drug_response",
    ]
    effect_summary: str  # one-liner describing what this variant does


GENES: dict[str, GeneEntry] = {
    "BRCA1": {
        "symbol": "BRCA1",
        "name": "Breast cancer type 1 susceptibility protein",
        "uniprot_id": "P38398",
        "role": "DNA double-strand break repair (homologous recombination). "
        "Germline pathogenic variants → elevated breast/ovarian cancer risk "
        "and PARP-inhibitor eligibility (synthetic lethality).",
    },
    "BRCA2": {
        "symbol": "BRCA2",
        "name": "Breast cancer type 2 susceptibility protein",
        "uniprot_id": "P51587",
        "role": "DNA double-strand break repair. Germline pathogenic variants "
        "→ elevated breast/ovarian cancer risk and PARP-inhibitor eligibility.",
    },
    "ESR1": {
        "symbol": "ESR1",
        "name": "Estrogen receptor alpha",
        "uniprot_id": "P03372",
        "role": "Hormone-dependent tumor driver in ER+ breast cancer. Target "
        "of tamoxifen (SERM) and fulvestrant (SERD). Acquired mutations in "
        "the ligand-binding domain (Y537S, D538G) drive endocrine resistance.",
    },
    "ERBB2": {
        "symbol": "ERBB2",
        "name": "Receptor tyrosine-protein kinase erbB-2 (HER2)",
        "uniprot_id": "P04626",
        "role": "Amplified/overexpressed in ~15–20% of breast cancers. Target "
        "of trastuzumab, pertuzumab, T-DM1. Activating kinase domain mutations "
        "(e.g. L755S, V777L) seen in HER2-low disease.",
    },
    "PIK3CA": {
        "symbol": "PIK3CA",
        "name": "Phosphatidylinositol 3-kinase catalytic subunit alpha",
        "uniprot_id": "P42336",
        "role": "Most frequently mutated oncogene in HR+ breast cancer "
        "(~40%). Hotspot mutations (H1047R, E545K, E542K) activate PI3K→AKT "
        "signaling and confer alpelisib sensitivity.",
    },
    "CYP2D6": {
        "symbol": "CYP2D6",
        "name": "Cytochrome P450 2D6",
        "uniprot_id": "P10635",
        "role": "Metabolizes tamoxifen into its active form, endoxifen. "
        "Poor metabolizers (*3/*4/*5/*6 homozygotes) convert ~60–90% less "
        "tamoxifen → endoxifen. CPIC recommends alternative endocrine "
        "therapy for PMs in premenopausal women.",
    },
    "DPYD": {
        "symbol": "DPYD",
        "name": "Dihydropyrimidine dehydrogenase",
        "uniprot_id": "Q12882",
        "role": "Catabolizes 5-fluorouracil (the active metabolite of "
        "capecitabine). Loss-of-function variants (*2A, *13, c.2846A>T, "
        "HapB3) cause severe, sometimes fatal fluoropyrimidine toxicity.",
    },
    "CYP19A1": {
        "symbol": "CYP19A1",
        "name": "Aromatase",
        "uniprot_id": "P11511",
        "role": "Converts androgens to estrogens. Target of letrozole, "
        "anastrozole, exemestane in postmenopausal ER+ breast cancer. Rare "
        "variants modestly affect estrogen levels and AI response.",
    },
}


DRUGS: dict[str, DrugEntry] = {
    "tamoxifen": {
        "id": "tamoxifen",
        "name": "Tamoxifen",
        "smiles": "CCC(=C(C1=CC=CC=C1)C2=CC=C(C=C2)OCCN(C)C)C3=CC=CC=C3",
        "category": "hormone_therapy",
        "primary_target_gene": "ESR1",
        "metabolizing_gene": "CYP2D6",
        "mechanism": "Selective estrogen-receptor modulator (SERM). In breast "
        "tissue tamoxifen acts as an ER antagonist, but it's a prodrug — "
        "clinical activity depends on CYP2D6-mediated conversion to endoxifen.",
        "breast_cancer_indication": "Adjuvant and metastatic treatment of ER+ breast "
        "cancer, especially in premenopausal women.",
    },
    "fulvestrant": {
        "id": "fulvestrant",
        "name": "Fulvestrant",
        "smiles": "CC(CCCC(C(F)(F)C(F)(F)F)S(=O)CCC)C1CCC2C1(CCC3C2CCC4=CC(=CC=C34)O)C",
        "category": "hormone_therapy",
        "primary_target_gene": "ESR1",
        "metabolizing_gene": None,
        "mechanism": "Selective estrogen-receptor degrader (SERD). Binds ER, "
        "induces conformational change → ubiquitination and proteasomal "
        "degradation of the receptor.",
        "breast_cancer_indication": "ER+/HER2- metastatic breast cancer, often with "
        "a CDK4/6 or PI3Kα inhibitor.",
    },
    "trastuzumab": {
        "id": "trastuzumab",
        "name": "Trastuzumab",
        # Antibodies don't have a SMILES. Use the Fab paratope's small-molecule
        # analog for the docking demo only. In production this entry would be
        # flagged as "antibody" and skip the docking step.
        "smiles": "",
        "category": "her2_targeted",
        "primary_target_gene": "ERBB2",
        "metabolizing_gene": None,
        "mechanism": "Monoclonal antibody against HER2 extracellular domain IV. "
        "Blocks ligand-independent HER2 signaling and flags cells for ADCC.",
        "breast_cancer_indication": "HER2-positive (IHC 3+ or FISH amplified) early "
        "and metastatic breast cancer.",
    },
    "palbociclib": {
        "id": "palbociclib",
        "name": "Palbociclib",
        "smiles": "CC(=O)C1=C(C)C2=CN=C(NC3=NC=C(C=C3)N3CCNCC3)N=C2N(C2CCCC2)C1=O",
        "category": "cdk46_inhibitor",
        "primary_target_gene": "CDK4",  # CDK4 not in GENES yet; we allow it
        "metabolizing_gene": None,
        "mechanism": "ATP-competitive CDK4/6 inhibitor → hypophosphorylates "
        "Rb → G1 cell-cycle arrest.",
        "breast_cancer_indication": "HR+/HER2- metastatic breast cancer with an "
        "aromatase inhibitor or fulvestrant.",
    },
    "olaparib": {
        "id": "olaparib",
        "name": "Olaparib",
        "smiles": "C1CC1C(=O)N2CCN(CC2)C(=O)C3=CC=CC(=C3CC4=NNC(=O)C5=CC=CC=C54)F",
        "category": "parp_inhibitor",
        "primary_target_gene": "BRCA1",  # proxy — PARP1 is the real target; BRCA1/2 loss is the context
        "metabolizing_gene": None,
        "mechanism": "PARP1/2 inhibitor → traps PARP on DNA → double-strand "
        "breaks that require BRCA-mediated homologous repair. In BRCA1/2-"
        "deficient cells, synthetic lethality.",
        "breast_cancer_indication": "Germline BRCA1/2-mutated HER2-negative "
        "metastatic breast cancer; adjuvant therapy in high-risk early BRCA+ disease.",
    },
    "alpelisib": {
        "id": "alpelisib",
        "name": "Alpelisib",
        "smiles": "CC(C)C1=NC(=C(S1)C(=O)NC2=NC=C(C=C2)C(F)(F)F)C3CCN(CC3)C(=O)C(=C)C",
        "category": "pi3k_inhibitor",
        "primary_target_gene": "PIK3CA",
        "metabolizing_gene": None,
        "mechanism": "Selective PI3Kα inhibitor. Particularly effective against "
        "hotspot-mutated PIK3CA (H1047R, E545K, E542K).",
        "breast_cancer_indication": "PIK3CA-mutated, HR+/HER2- metastatic breast "
        "cancer (with fulvestrant).",
    },
    "letrozole": {
        "id": "letrozole",
        "name": "Letrozole",
        "smiles": "C1=CC(=CC=C1C(C#N)C2=CN=CN2)C(C#N)C3=CC=C(C=C3)C#N",
        "category": "aromatase_inhibitor",
        "primary_target_gene": "CYP19A1",
        "metabolizing_gene": None,
        "mechanism": "Non-steroidal aromatase inhibitor → blocks androgen → "
        "estrogen conversion → suppresses peripheral estrogen in "
        "postmenopausal women.",
        "breast_cancer_indication": "Postmenopausal HR+ early and metastatic "
        "breast cancer.",
    },
    "capecitabine": {
        "id": "capecitabine",
        "name": "Capecitabine",
        "smiles": "CCCCCOC(=O)NC1=NC(=O)N(C=C1F)C2C(C(C(O2)C)O)O",
        "category": "chemotherapy",
        "primary_target_gene": "DPYD",  # DPYD handles the clearance step, not the target
        "metabolizing_gene": "DPYD",
        "mechanism": "Oral prodrug of 5-FU → thymidylate synthase inhibition. "
        "DPYD deficiency causes 5-FU accumulation and severe toxicity.",
        "breast_cancer_indication": "Metastatic breast cancer after anthracycline/"
        "taxane failure, or in triple-negative disease.",
    },
}


# Hand-picked variants that are (a) high clinical evidence and
# (b) either pocket-resident or metabolism-altering — so they make the demo
# meaningful rather than cosmetic.
VARIANTS: dict[str, VariantEntry] = {
    # --- BRCA1 ---
    "BRCA1_185delAG": {
        "id": "BRCA1_185delAG",
        "gene_symbol": "BRCA1",
        "name": "BRCA1 c.68_69delAG (185delAG)",
        "hgvs_protein": "p.Glu23ValfsTer17",
        "residue_positions": [23],
        "clinical_significance": "pathogenic",
        "effect_summary": "Ashkenazi founder frameshift. Produces truncated, "
        "non-functional BRCA1. PARP-inhibitor eligibility if tumor is breast/ovarian.",
    },
    "BRCA1_C61G": {
        "id": "BRCA1_C61G",
        "gene_symbol": "BRCA1",
        "name": "BRCA1 p.Cys61Gly",
        "hgvs_protein": "p.C61G",
        "residue_positions": [61],
        "clinical_significance": "pathogenic",
        "effect_summary": "Disrupts RING domain zinc coordination → loss of "
        "E3 ligase function. Classic missense loss-of-function.",
    },
    # --- BRCA2 ---
    "BRCA2_6174delT": {
        "id": "BRCA2_6174delT",
        "gene_symbol": "BRCA2",
        "name": "BRCA2 c.5946delT (6174delT)",
        "hgvs_protein": "p.Ser1982ArgfsTer22",
        "residue_positions": [1982],
        "clinical_significance": "pathogenic",
        "effect_summary": "Ashkenazi founder frameshift → truncated BRCA2, "
        "loss of RAD51 binding → HR-deficient tumor context.",
    },
    # --- ESR1 (endocrine resistance) ---
    "ESR1_Y537S": {
        "id": "ESR1_Y537S",
        "gene_symbol": "ESR1",
        "name": "ESR1 p.Tyr537Ser",
        "hgvs_protein": "p.Y537S",
        "residue_positions": [537],
        "clinical_significance": "drug_response",
        "effect_summary": "Constitutively active ER mutant. Confers resistance "
        "to aromatase inhibitors; reduced but partial response to fulvestrant. "
        "Acquired in ~20% of endocrine-pretreated metastatic ER+ disease.",
    },
    "ESR1_D538G": {
        "id": "ESR1_D538G",
        "gene_symbol": "ESR1",
        "name": "ESR1 p.Asp538Gly",
        "hgvs_protein": "p.D538G",
        "residue_positions": [538],
        "clinical_significance": "drug_response",
        "effect_summary": "Ligand-independent ER activation → aromatase-inhibitor "
        "resistance. Most common ESR1 acquired mutation.",
    },
    # --- ERBB2 (HER2) ---
    "ERBB2_L755S": {
        "id": "ERBB2_L755S",
        "gene_symbol": "ERBB2",
        "name": "HER2 p.Leu755Ser",
        "hgvs_protein": "p.L755S",
        "residue_positions": [755],
        "clinical_significance": "drug_response",
        "effect_summary": "Kinase-domain activating mutation. Sensitive to "
        "neratinib/tucatinib; may confer lapatinib resistance.",
    },
    "ERBB2_V777L": {
        "id": "ERBB2_V777L",
        "gene_symbol": "ERBB2",
        "name": "HER2 p.Val777Leu",
        "hgvs_protein": "p.V777L",
        "residue_positions": [777],
        "clinical_significance": "drug_response",
        "effect_summary": "Activating kinase-domain mutation in HER2-low disease. "
        "Preclinical sensitivity to irreversible TKIs.",
    },
    # --- PIK3CA ---
    "PIK3CA_H1047R": {
        "id": "PIK3CA_H1047R",
        "gene_symbol": "PIK3CA",
        "name": "PIK3CA p.His1047Arg",
        "hgvs_protein": "p.H1047R",
        "residue_positions": [1047],
        "clinical_significance": "drug_response",
        "effect_summary": "Kinase-domain hotspot. Activating gain-of-function. "
        "FDA-approved biomarker for alpelisib + fulvestrant.",
    },
    "PIK3CA_E545K": {
        "id": "PIK3CA_E545K",
        "gene_symbol": "PIK3CA",
        "name": "PIK3CA p.Glu545Lys",
        "hgvs_protein": "p.E545K",
        "residue_positions": [545],
        "clinical_significance": "drug_response",
        "effect_summary": "Helical-domain hotspot. Activating. FDA-approved "
        "biomarker for alpelisib.",
    },
    # --- CYP2D6 star alleles (tamoxifen metabolism) ---
    "CYP2D6_star4": {
        "id": "CYP2D6_star4",
        "gene_symbol": "CYP2D6",
        "name": "CYP2D6*4 (c.1846G>A, splice defect)",
        "hgvs_protein": None,
        "residue_positions": [],
        "clinical_significance": "drug_response",
        "effect_summary": "Null allele. Homozygotes are poor metabolizers — "
        "substantially reduced tamoxifen → endoxifen conversion. CPIC Level A: "
        "recommend alternative endocrine therapy in premenopausal patients.",
    },
    "CYP2D6_star10": {
        "id": "CYP2D6_star10",
        "gene_symbol": "CYP2D6",
        "name": "CYP2D6*10 (p.Pro34Ser + c.1846G>A)",
        "hgvs_protein": "p.P34S",
        "residue_positions": [34],
        "clinical_significance": "drug_response",
        "effect_summary": "Decreased-function allele (common in East Asian "
        "populations). Intermediate metabolizer phenotype in homozygotes.",
    },
    # --- DPYD (fluoropyrimidine toxicity) ---
    "DPYD_star2A": {
        "id": "DPYD_star2A",
        "gene_symbol": "DPYD",
        "name": "DPYD*2A (c.1905+1G>A, splice donor loss)",
        "hgvs_protein": None,
        "residue_positions": [],
        "clinical_significance": "drug_response",
        "effect_summary": "Complete DPD loss-of-function. Heterozygotes need "
        "~50% capecitabine dose reduction; homozygotes should avoid the drug. "
        "CPIC Level A.",
    },
    "DPYD_c2846A_T": {
        "id": "DPYD_c2846A_T",
        "gene_symbol": "DPYD",
        "name": "DPYD c.2846A>T (p.Asp949Val)",
        "hgvs_protein": "p.D949V",
        "residue_positions": [949],
        "clinical_significance": "drug_response",
        "effect_summary": "Reduced DPD activity. CPIC recommends ~50% "
        "capecitabine dose reduction in heterozygotes.",
    },
}


# CPIC / FDA-label style drug-gene-variant guidance. Hand-curated from public
# CPIC guidelines (tamoxifen/CYP2D6 guideline, capecitabine/DPYD guideline,
# PIK3CA-alpelisib FDA label, BRCA-olaparib FDA label, ESR1 resistance literature).
class PGxRule(TypedDict):
    drug_id: str
    gene_symbol: str
    variant_ids: list[str]  # which variants in VARIANTS this rule applies to
    # Genotype assumptions: single heterozygous or two-copy.
    genotype: Literal["heterozygous", "homozygous", "any"]
    phenotype: str  # e.g. "poor metabolizer", "intermediate metabolizer"
    recommendation: str
    evidence_level: Literal["A", "B", "C", "D"]
    source: str


PGX_RULES: list[PGxRule] = [
    # --- Tamoxifen / CYP2D6 (CPIC) ---
    {
        "drug_id": "tamoxifen",
        "gene_symbol": "CYP2D6",
        "variant_ids": ["CYP2D6_star4"],
        "genotype": "homozygous",
        "phenotype": "poor metabolizer",
        "recommendation": "CPIC recommends an alternative hormonal therapy "
        "(e.g. aromatase inhibitor for postmenopausal, ovarian suppression "
        "+ AI for premenopausal). Tamoxifen efficacy is substantially reduced.",
        "evidence_level": "A",
        "source": "CPIC 2018 tamoxifen/CYP2D6 guideline",
    },
    {
        "drug_id": "tamoxifen",
        "gene_symbol": "CYP2D6",
        "variant_ids": ["CYP2D6_star4", "CYP2D6_star10"],
        "genotype": "heterozygous",
        "phenotype": "intermediate metabolizer",
        "recommendation": "CPIC: consider higher tamoxifen dose (40 mg/day) "
        "where tolerated, or alternative endocrine therapy. Data strongest in "
        "premenopausal patients.",
        "evidence_level": "A",
        "source": "CPIC 2018 tamoxifen/CYP2D6 guideline",
    },
    # --- Capecitabine / DPYD (CPIC) ---
    {
        "drug_id": "capecitabine",
        "gene_symbol": "DPYD",
        "variant_ids": ["DPYD_star2A"],
        "genotype": "heterozygous",
        "phenotype": "intermediate DPD activity",
        "recommendation": "CPIC: reduce starting dose by ~50% and titrate up. "
        "Severe/fatal toxicity risk without dose reduction.",
        "evidence_level": "A",
        "source": "CPIC 2017 fluoropyrimidines/DPYD guideline (updated)",
    },
    {
        "drug_id": "capecitabine",
        "gene_symbol": "DPYD",
        "variant_ids": ["DPYD_star2A"],
        "genotype": "homozygous",
        "phenotype": "DPD deficiency",
        "recommendation": "CPIC: avoid fluoropyrimidines. Use an alternative "
        "regimen. Homozygous DPD deficiency carries risk of fatal toxicity.",
        "evidence_level": "A",
        "source": "CPIC 2017 fluoropyrimidines/DPYD guideline",
    },
    {
        "drug_id": "capecitabine",
        "gene_symbol": "DPYD",
        "variant_ids": ["DPYD_c2846A_T"],
        "genotype": "heterozygous",
        "phenotype": "intermediate DPD activity",
        "recommendation": "CPIC: ~50% dose reduction with titration.",
        "evidence_level": "A",
        "source": "CPIC 2017 fluoropyrimidines/DPYD guideline",
    },
    # --- Olaparib / BRCA1 / BRCA2 (FDA label, OlympiA trial) ---
    {
        "drug_id": "olaparib",
        "gene_symbol": "BRCA1",
        "variant_ids": ["BRCA1_185delAG", "BRCA1_C61G"],
        "genotype": "heterozygous",
        "phenotype": "germline BRCA1 pathogenic carrier",
        "recommendation": "FDA-approved indication. Olaparib is eligible for "
        "HER2-negative high-risk early or metastatic breast cancer with a "
        "germline BRCA1/2 pathogenic variant. Tumor second-hit confers "
        "HR-deficiency and synthetic lethality.",
        "evidence_level": "A",
        "source": "FDA olaparib label + OlympiA (NEJM 2021)",
    },
    {
        "drug_id": "olaparib",
        "gene_symbol": "BRCA2",
        "variant_ids": ["BRCA2_6174delT"],
        "genotype": "heterozygous",
        "phenotype": "germline BRCA2 pathogenic carrier",
        "recommendation": "FDA-approved indication (see BRCA1 note — applies "
        "to either gene).",
        "evidence_level": "A",
        "source": "FDA olaparib label + OlympiA",
    },
    # --- Alpelisib / PIK3CA (FDA SOLAR-1) ---
    {
        "drug_id": "alpelisib",
        "gene_symbol": "PIK3CA",
        "variant_ids": ["PIK3CA_H1047R", "PIK3CA_E545K"],
        "genotype": "heterozygous",
        "phenotype": "PIK3CA-mutated tumor",
        "recommendation": "FDA-approved biomarker. Alpelisib + fulvestrant in "
        "HR+/HER2-, PIK3CA-mutated metastatic breast cancer after endocrine "
        "progression.",
        "evidence_level": "A",
        "source": "FDA alpelisib label (SOLAR-1, NEJM 2019)",
    },
    # --- Fulvestrant / ESR1 (resistance literature) ---
    {
        "drug_id": "fulvestrant",
        "gene_symbol": "ESR1",
        "variant_ids": ["ESR1_Y537S", "ESR1_D538G"],
        "genotype": "any",
        "phenotype": "acquired endocrine resistance",
        "recommendation": "Reduced but preserved response to fulvestrant vs "
        "aromatase inhibitors. Emerging oral SERDs (elacestrant) target "
        "ESR1-mutated disease specifically (EMERALD, FDA 2023).",
        "evidence_level": "B",
        "source": "EMERALD, PADA-1 trials; ASCO 2022–2023",
    },
    # --- Trastuzumab / ERBB2 ---
    {
        "drug_id": "trastuzumab",
        "gene_symbol": "ERBB2",
        "variant_ids": ["ERBB2_L755S", "ERBB2_V777L"],
        "genotype": "any",
        "phenotype": "HER2 activating kinase mutation",
        "recommendation": "Trastuzumab (targets extracellular domain) retains "
        "activity. Consider adding a HER2 TKI (neratinib, tucatinib) targeting "
        "the mutant kinase domain.",
        "evidence_level": "B",
        "source": "MutHER, SUMMIT basket trials",
    },
]


def rules_for_drug(drug_id: str) -> list[PGxRule]:
    return [r for r in PGX_RULES if r["drug_id"] == drug_id]


def variants_for_gene(gene_symbol: str) -> list[VariantEntry]:
    return [v for v in VARIANTS.values() if v["gene_symbol"] == gene_symbol]
