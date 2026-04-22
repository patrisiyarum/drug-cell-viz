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
    primary_target_gene: str  # symbol from GENES — what the drug physically binds
    metabolizing_gene: str | None  # gene whose variants affect metabolism
    # Genes whose status matters clinically even though the drug doesn't bind
    # them. Used for synthetic-lethality drugs (olaparib → BRCA1/BRCA2) so
    # the relevance check knows a BRCA1 variant IS part of olaparib's story
    # even though the drug physically binds PARP1.
    context_genes: list[str]
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
        "role": "DNA double-strand break repair via homologous recombination. "
        "Germline pathogenic variants drive roughly 55-70% lifetime breast "
        "cancer risk and 40-45% lifetime ovarian cancer risk. Loss of BRCA1 "
        "function creates the HR-deficient state that PARP inhibitors "
        "(olaparib, niraparib, rucaparib) exploit via synthetic lethality "
        "in both breast AND ovarian tumors.",
    },
    "BRCA2": {
        "symbol": "BRCA2",
        "name": "Breast cancer type 2 susceptibility protein",
        "uniprot_id": "P51587",
        "role": "DNA double-strand break repair. Germline pathogenic variants "
        "confer ~45-70% lifetime breast cancer risk and ~15-25% lifetime "
        "ovarian cancer risk. Like BRCA1, BRCA2 loss creates HR deficiency, "
        "qualifying the tumor for PARP-inhibitor therapy across breast, "
        "ovarian, pancreatic, and prostate indications.",
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
    "TYMS": {
        "symbol": "TYMS",
        "name": "Thymidylate synthase",
        "uniprot_id": "P04818",
        "role": "Catalyzes dUMP → dTMP, essential for DNA synthesis. Inhibited "
        "by 5-fluorouracil (5-FU), the active metabolite of capecitabine. "
        "TS-inhibition is the primary mechanism of fluoropyrimidine cytotoxicity.",
    },
    "PALB2": {
        "symbol": "PALB2",
        "name": "Partner and localizer of BRCA2",
        "uniprot_id": "Q86YC2",
        "role": "Bridges BRCA1 and BRCA2 during homologous-recombination DNA "
        "repair. Germline pathogenic variants confer ~50% lifetime breast "
        "cancer risk and qualify tumors for PARP-inhibitor therapy. Third "
        "major HR gene after BRCA1 and BRCA2.",
    },
    "CHEK2": {
        "symbol": "CHEK2",
        "name": "Checkpoint kinase 2",
        "uniprot_id": "O96017",
        "role": "DNA-damage-response kinase activated by ATM. Germline "
        "pathogenic variants (most commonly c.1100delC) approximately double "
        "breast cancer risk. Moderate-penetrance gene; routinely screened "
        "on clinical hereditary-cancer panels.",
    },
    "AKT1": {
        "symbol": "AKT1",
        "name": "RAC-alpha serine/threonine-protein kinase",
        "uniprot_id": "P31749",
        "role": "Central node of the PI3K/AKT/mTOR survival pathway. The "
        "E17K hotspot mutation locks AKT1 at the plasma membrane in an "
        "active conformation and drives ER+ breast cancer growth. Target "
        "of capivasertib (FDA 2023, CAPItello-291).",
    },
    "PARP1": {
        "symbol": "PARP1",
        "name": "Poly [ADP-ribose] polymerase 1",
        "uniprot_id": "P09874",
        "role": "DNA-damage sensor that flags single-strand breaks for repair. "
        "Target of olaparib, talazoparib, rucaparib. PARP inhibition is "
        "synthetically lethal in HR-deficient cells (BRCA1/2 pathogenic "
        "tumors) because unrepaired double-strand breaks accumulate.",
    },
    # --- Extended HR pathway (moderate-penetrance + Fanconi anemia family) ---
    "ATM": {
        "symbol": "ATM",
        "name": "Ataxia-telangiectasia mutated kinase",
        "uniprot_id": "Q13315",
        "role": "Upstream kinase that activates the DNA-damage response. "
        "Germline pathogenic variants elevate breast and pancreatic cancer "
        "risk. Some ATM-mutant tumors show partial HR deficiency, but ATM "
        "alone is not a reliable PARPi biomarker.",
    },
    "RAD51C": {
        "symbol": "RAD51C",
        "name": "RAD51 paralog C",
        "uniprot_id": "O43502",
        "role": "Component of the RAD51 paralog complex that drives the "
        "actual strand-invasion step of homologous recombination. Germline "
        "pathogenic variants confer elevated ovarian and triple-negative "
        "breast cancer risk. Recognized PARPi-eligible gene per FDA label.",
    },
    "RAD51D": {
        "symbol": "RAD51D",
        "name": "RAD51 paralog D",
        "uniprot_id": "O75771",
        "role": "RAD51 paralog that works with RAD51C. Germline pathogenic "
        "variants raise ovarian cancer risk markedly. FDA-recognized "
        "PARPi-eligible gene.",
    },
    "BRIP1": {
        "symbol": "BRIP1",
        "name": "BRCA1-interacting protein 1 (FANCJ)",
        "uniprot_id": "Q9BX63",
        "role": "Helicase that partners with BRCA1 in HR repair. Also known "
        "as FANCJ in the Fanconi anemia family. Germline pathogenic variants "
        "elevate ovarian cancer risk and contribute to HR deficiency.",
    },
    "BARD1": {
        "symbol": "BARD1",
        "name": "BRCA1-associated RING domain protein 1",
        "uniprot_id": "Q99728",
        "role": "Obligate heterodimer partner of BRCA1. BARD1 loss phenocopies "
        "BRCA1 loss in terms of HR deficiency. Germline pathogenic variants "
        "elevate breast cancer risk.",
    },
    "FANCA": {
        "symbol": "FANCA",
        "name": "Fanconi anemia complementation group A",
        "uniprot_id": "O15360",
        "role": "Core component of the Fanconi anemia complex that "
        "activates FANCD2/FANCI for inter-strand crosslink repair. Biallelic "
        "loss causes Fanconi anemia; monoallelic germline variants may "
        "contribute to HR deficiency in some tumors.",
    },
    "FANCC": {
        "symbol": "FANCC",
        "name": "Fanconi anemia complementation group C",
        "uniprot_id": "Q00597",
        "role": "Core FA complex component. Ashkenazi founder variant "
        "(c.456+4A>T) is relatively common. Same HR-related logic as "
        "other FA family genes.",
    },
    "FANCD2": {
        "symbol": "FANCD2",
        "name": "Fanconi anemia complementation group D2",
        "uniprot_id": "Q9BXW9",
        "role": "Monoubiquitinated by the FA core complex to trigger "
        "inter-strand crosslink repair in coordination with BRCA1/BRCA2. "
        "Central to the Fanconi anemia / BRCA pathway.",
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
        "tissue tamoxifen acts as an ER antagonist, but it's a prodrug. "
        "clinical activity depends on CYP2D6-mediated conversion to endoxifen.",
        "context_genes": [],
        "breast_cancer_indication":"Adjuvant and metastatic treatment of ER+ breast "
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
        "context_genes": [],
        "breast_cancer_indication":"ER+/HER2- metastatic breast cancer, often with "
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
        "context_genes": [],
        "breast_cancer_indication":"HER2-positive (IHC 3+ or FISH amplified) early "
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
        "context_genes": [],
        "breast_cancer_indication":"HR+/HER2- metastatic breast cancer with an "
        "aromatase inhibitor or fulvestrant.",
    },
    "olaparib": {
        "id": "olaparib",
        "name": "Olaparib",
        "smiles": "C1CC1C(=O)N2CCN(CC2)C(=O)C3=CC=CC(=C3CC4=NNC(=O)C5=CC=CC=C54)F",
        "category": "parp_inhibitor",
        # Olaparib binds PARP1, not BRCA1. The BRCA1/2 connection is via
        # synthetic lethality — HR-deficient cells can't repair the DSBs
        # that PARP inhibition causes. The app's BRCA1 variant-effect
        # classifier is what surfaces the BRCA1 relevance separately.
        "primary_target_gene": "PARP1",
        "metabolizing_gene": None,
        "mechanism": "Traps PARP1/2 on DNA, causing double-strand breaks "
        "that require BRCA-mediated homologous repair to fix. In BRCA1/2-"
        "deficient cells, those breaks are lethal (synthetic lethality).",
        "context_genes": ["BRCA1", "BRCA2", "PALB2"],
        "breast_cancer_indication": "FDA-approved across both breast AND "
        "ovarian cancer. Breast: germline BRCA1/2-mutated HER2-negative "
        "metastatic or high-risk early disease (OlympiA, OlympiAD). "
        "Ovarian: first-line maintenance in BRCA1/2-mutated advanced "
        "ovarian cancer after platinum response (SOLO-1).",
    },
    "niraparib": {
        "id": "niraparib",
        "name": "Niraparib (Zejula)",
        "smiles": (
            "C1CCC(CC1)C2=CC3=C(C=C2)N(NC3=O)CC4=CC=C(C=C4)C(=N)N"
        ),
        "category": "parp_inhibitor",
        "primary_target_gene": "PARP1",
        "metabolizing_gene": None,
        "mechanism": "PARP1/2 inhibitor. Broader ovarian approval than "
        "olaparib — works as maintenance after platinum response regardless "
        "of BRCA status, though BRCA+/HRD+ tumors benefit most.",
        "context_genes": ["BRCA1", "BRCA2", "PALB2"],
        "breast_cancer_indication": "Primarily used in advanced ovarian "
        "cancer (first-line and later-line maintenance, both BRCA-mutated "
        "and HR-proficient). Included here as the prototypical ovarian "
        "PARP inhibitor in the broader HR-deficient cancer framework this "
        "tool covers alongside olaparib.",
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
        "context_genes": [],
        "breast_cancer_indication":"PIK3CA-mutated, HR+/HER2- metastatic breast "
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
        "context_genes": [],
        "breast_cancer_indication":"Postmenopausal HR+ early and metastatic "
        "breast cancer.",
    },
    "capecitabine": {
        "id": "capecitabine",
        "name": "Capecitabine (Xeloda)",
        # For the 3D view we dock 5-fluorouracil (the active metabolite) into
        # thymidylate synthase. Capecitabine itself is a prodrug and doesn't
        # bind TS directly. This gives a biologically meaningful docking pose.
        "smiles": "C1=C(C(=O)NC(=O)N1)F",  # 5-FU
        "category": "chemotherapy",
        "primary_target_gene": "TYMS",
        "metabolizing_gene": "DPYD",
        "mechanism": "Oral prodrug of 5-FU. 5-FU → FdUMP → thymidylate "
        "synthase inhibition → disrupts DNA synthesis. DPYD deficiency causes "
        "5-FU accumulation and severe, sometimes fatal toxicity.",
        "context_genes": [],
        "breast_cancer_indication": "Metastatic breast cancer, especially "
        "triple-negative disease, after anthracycline/taxane failure. DPYD "
        "genotyping before starting is increasingly standard of care.",
    },
    "elacestrant": {
        "id": "elacestrant",
        "name": "Elacestrant (Orserdu)",
        "smiles": (
            "CCN(CC1)CCC1(C2=CC=CC(=C2)O)C3=CC=C(C(=C3)O)C(CCN4CCCCC4)C"
        ),
        "category": "hormone_therapy",
        "primary_target_gene": "ESR1",
        "metabolizing_gene": None,
        "mechanism": "Oral selective estrogen receptor degrader (SERD). "
        "Binds ER, induces receptor degradation, and remains active against "
        "ESR1 ligand-binding-domain mutants (Y537S, D538G) that drive "
        "resistance to aromatase inhibitors.",
        "context_genes": [],
        "breast_cancer_indication": "FDA-approved 2023 for ER+/HER2- "
        "advanced breast cancer with an ESR1 mutation, after one prior "
        "line of endocrine therapy.",
    },
    "capivasertib": {
        "id": "capivasertib",
        "name": "Capivasertib (Truqap)",
        "smiles": (
            "C1CC(NC(=O)C1)C2=CC=C(C=C2)C3=NC=NC4=C3C=CN4CC(=O)NC5CCCCC5N"
        ),
        "category": "pi3k_inhibitor",  # reuses the bucket; it's technically AKT
        "primary_target_gene": "AKT1",
        "metabolizing_gene": None,
        "mechanism": "ATP-competitive, selective inhibitor of all three AKT "
        "isoforms (AKT1/2/3). Blocks the AKT node in the PI3K/AKT/mTOR "
        "pathway that drives ER+ breast cancer growth, especially in tumors "
        "with activating AKT1, PIK3CA, or PTEN alterations.",
        "context_genes": ["PIK3CA", "PTEN"],
        "breast_cancer_indication": "FDA-approved 2023 with fulvestrant for "
        "HR+/HER2- advanced breast cancer harboring AKT1/PIK3CA/PTEN "
        "alterations, after endocrine-therapy progression (CAPItello-291).",
    },
    "trastuzumab_deruxtecan": {
        "id": "trastuzumab_deruxtecan",
        "name": "Trastuzumab deruxtecan (Enhertu)",
        "smiles": "",  # antibody-drug conjugate; don't dock
        "category": "her2_targeted",
        "primary_target_gene": "ERBB2",
        "metabolizing_gene": None,
        "mechanism": "HER2-targeted antibody-drug conjugate. Trastuzumab "
        "carries a topoisomerase-I-inhibitor payload (DXd) directly to "
        "HER2-expressing cells, where it's cleaved and kills the cell. "
        "Active even against HER2-LOW (IHC 1+ or 2+/ISH-) tumors, expanding "
        "the treatable HER2 population beyond classical HER2+.",
        "context_genes": [],
        "breast_cancer_indication": "FDA-approved 2022 (DESTINY-Breast04) "
        "for HER2-low metastatic breast cancer and for classical HER2+ "
        "disease after prior anti-HER2 therapy.",
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
        "effect_summary": "Null allele. Homozygotes are poor metabolizers, "
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
    # --- PALB2 (hereditary breast cancer, PARPi eligibility) ---
    "PALB2_1592delT": {
        "id": "PALB2_1592delT",
        "gene_symbol": "PALB2",
        "name": "PALB2 c.1592delT (Finnish founder)",
        "hgvs_protein": "p.Leu531CysfsTer30",
        "residue_positions": [531],
        "clinical_significance": "pathogenic",
        "effect_summary": "Frameshift variant prevalent in Finnish populations. "
        "Truncates PALB2 before its WD40 BRCA2-binding domain, abolishing "
        "homologous-recombination repair. ~50% lifetime breast cancer risk "
        "in heterozygous carriers.",
    },
    "PALB2_3113G_A": {
        "id": "PALB2_3113G_A",
        "gene_symbol": "PALB2",
        "name": "PALB2 c.3113G>A (p.Trp1038Ter)",
        "hgvs_protein": "p.W1038*",
        "residue_positions": [1038],
        "clinical_significance": "pathogenic",
        "effect_summary": "Nonsense variant in the WD40 domain disrupts the "
        "BRCA2 interaction surface. Recurrently observed in hereditary "
        "breast and pancreatic cancer families.",
    },
    # --- CHEK2 (moderate-penetrance breast cancer) ---
    "CHEK2_1100delC": {
        "id": "CHEK2_1100delC",
        "gene_symbol": "CHEK2",
        "name": "CHEK2 c.1100delC (Northern European founder)",
        "hgvs_protein": "p.Thr367MetfsTer15",
        "residue_positions": [367],
        "clinical_significance": "pathogenic",
        "effect_summary": "Frameshift in the kinase domain truncates CHEK2. "
        "Approximately doubles lifetime breast cancer risk in female "
        "carriers and modestly elevates risk in male carriers. Common "
        "founder variant on routine hereditary-cancer panels.",
    },
    "CHEK2_I157T": {
        "id": "CHEK2_I157T",
        "gene_symbol": "CHEK2",
        "name": "CHEK2 p.Ile157Thr",
        "hgvs_protein": "p.I157T",
        "residue_positions": [157],
        "clinical_significance": "pathogenic",
        "effect_summary": "Missense change in the FHA domain. Lower penetrance "
        "than 1100delC but still elevates breast and prostate cancer risk. "
        "Most common in Slavic populations.",
    },
    # --- AKT1 (hotspot, capivasertib biomarker) ---
    "AKT1_E17K": {
        "id": "AKT1_E17K",
        "gene_symbol": "AKT1",
        "name": "AKT1 p.Glu17Lys",
        "hgvs_protein": "p.E17K",
        "residue_positions": [17],
        "clinical_significance": "drug_response",
        "effect_summary": "Activating hotspot in the PH domain. Locks AKT1 "
        "at the membrane in a constitutively active conformation. Occurs "
        "in ~6% of ER+ breast cancers and is an FDA-recognized biomarker "
        "for capivasertib (CAPItello-291).",
    },
    # --- Extended HR pathway variants ---
    "ATM_R2832C": {
        "id": "ATM_R2832C",
        "gene_symbol": "ATM",
        "name": "ATM p.Arg2832Cys",
        "hgvs_protein": "p.R2832C",
        "residue_positions": [2832],
        "clinical_significance": "pathogenic",
        "effect_summary": "Recurrent ATM missense in the PI3K-like kinase "
        "domain. Associated with ataxia-telangiectasia when homozygous and "
        "with elevated breast cancer risk in heterozygous carriers.",
    },
    "RAD51C_R237W": {
        "id": "RAD51C_R237W",
        "gene_symbol": "RAD51C",
        "name": "RAD51C p.Arg237Trp",
        "hgvs_protein": "p.R237W",
        "residue_positions": [237],
        "clinical_significance": "pathogenic",
        "effect_summary": "Missense in the Walker A domain disrupts ATP "
        "binding. Associated with hereditary ovarian cancer.",
    },
    "RAD51D_R232X": {
        "id": "RAD51D_R232X",
        "gene_symbol": "RAD51D",
        "name": "RAD51D p.Arg232Ter",
        "hgvs_protein": "p.R232*",
        "residue_positions": [232],
        "clinical_significance": "pathogenic",
        "effect_summary": "Nonsense variant truncates RAD51D before the "
        "ATP-binding region. Recurrent in hereditary ovarian cancer families.",
    },
    "BRIP1_R798X": {
        "id": "BRIP1_R798X",
        "gene_symbol": "BRIP1",
        "name": "BRIP1 p.Arg798Ter",
        "hgvs_protein": "p.R798*",
        "residue_positions": [798],
        "clinical_significance": "pathogenic",
        "effect_summary": "Nonsense variant eliminates the helicase C-"
        "terminus. Recurrent in hereditary ovarian cancer.",
    },
    "BARD1_Q564X": {
        "id": "BARD1_Q564X",
        "gene_symbol": "BARD1",
        "name": "BARD1 p.Gln564Ter",
        "hgvs_protein": "p.Q564*",
        "residue_positions": [564],
        "clinical_significance": "pathogenic",
        "effect_summary": "Nonsense variant disrupting the BRCT domains "
        "that BRCA1-dependent E3 ligase activity requires.",
    },
    "FANCC_IVS4_1G_T": {
        "id": "FANCC_IVS4_1G_T",
        "gene_symbol": "FANCC",
        "name": "FANCC c.456+4A>T (Ashkenazi founder)",
        "hgvs_protein": None,
        "residue_positions": [],
        "clinical_significance": "pathogenic",
        "effect_summary": "Splice-site variant; most common FANCC pathogenic "
        "variant in Ashkenazi Jewish populations. Associated with Fanconi "
        "anemia when biallelic.",
    },
    "FANCA_H1110P": {
        "id": "FANCA_H1110P",
        "gene_symbol": "FANCA",
        "name": "FANCA p.His1110Pro",
        "hgvs_protein": "p.H1110P",
        "residue_positions": [1110],
        "clinical_significance": "pathogenic",
        "effect_summary": "Recurrent FANCA missense in the C-terminal region "
        "of the FA core complex. Biallelic variants cause Fanconi anemia.",
    },
    "FANCD2_E734X": {
        "id": "FANCD2_E734X",
        "gene_symbol": "FANCD2",
        "name": "FANCD2 p.Glu734Ter",
        "hgvs_protein": "p.E734*",
        "residue_positions": [734],
        "clinical_significance": "pathogenic",
        "effect_summary": "Nonsense variant truncating FANCD2 before the "
        "monoubiquitination site essential for FA pathway activation.",
    },
    # --- ESR1 (additional resistance mutations, elacestrant biomarkers) ---
    "ESR1_Y537N": {
        "id": "ESR1_Y537N",
        "gene_symbol": "ESR1",
        "name": "ESR1 p.Tyr537Asn",
        "hgvs_protein": "p.Y537N",
        "residue_positions": [537],
        "clinical_significance": "drug_response",
        "effect_summary": "Ligand-independent ER activation, same mechanism "
        "as Y537S. Confers aromatase-inhibitor resistance. Retains partial "
        "response to elacestrant (EMERALD).",
    },
    "ESR1_L536P": {
        "id": "ESR1_L536P",
        "gene_symbol": "ESR1",
        "name": "ESR1 p.Leu536Pro",
        "hgvs_protein": "p.L536P",
        "residue_positions": [536],
        "clinical_significance": "drug_response",
        "effect_summary": "Helix 12 mutation that stabilizes the agonist "
        "conformation without estrogen. Less common than Y537S/D538G but "
        "same clinical implication of endocrine resistance.",
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
    # --- Olaparib / BRCA1 / BRCA2 (FDA label, OlympiA + SOLO-1) ---
    {
        "drug_id": "olaparib",
        "gene_symbol": "BRCA1",
        "variant_ids": ["BRCA1_185delAG", "BRCA1_C61G"],
        "genotype": "heterozygous",
        "phenotype": "germline BRCA1 pathogenic carrier",
        "recommendation": "FDA-approved across both breast AND ovarian "
        "cancer for germline BRCA1 pathogenic carriers. Breast: HER2-negative "
        "high-risk early or metastatic disease (OlympiA, OlympiAD). Ovarian: "
        "first-line maintenance after platinum response (SOLO-1). The tumor "
        "second-hit BRCA1 inactivation creates HR deficiency and synthetic "
        "lethality with PARP inhibition.",
        "evidence_level": "A",
        "source": "FDA olaparib label; OlympiA (NEJM 2021); SOLO-1 (NEJM 2018)",
    },
    {
        "drug_id": "olaparib",
        "gene_symbol": "BRCA2",
        "variant_ids": ["BRCA2_6174delT"],
        "genotype": "heterozygous",
        "phenotype": "germline BRCA2 pathogenic carrier",
        "recommendation": "FDA-approved indication. Same breast + ovarian "
        "eligibility as germline BRCA1. BRCA2 carriers additionally qualify "
        "for olaparib in BRCA-mutated pancreatic (POLO) and metastatic "
        "castration-resistant prostate cancer (PROfound).",
        "evidence_level": "A",
        "source": "FDA olaparib label; OlympiA; POLO; PROfound",
    },
    # --- Niraparib / BRCA1 / BRCA2 (ovarian maintenance) ---
    {
        "drug_id": "niraparib",
        "gene_symbol": "BRCA1",
        "variant_ids": ["BRCA1_185delAG", "BRCA1_C61G"],
        "genotype": "heterozygous",
        "phenotype": "germline BRCA1 pathogenic carrier",
        "recommendation": "FDA-approved for ovarian cancer maintenance "
        "therapy. BRCA-mutated carriers had the largest progression-free "
        "survival benefit in PRIMA and NOVA.",
        "evidence_level": "A",
        "source": "FDA niraparib label; PRIMA (NEJM 2019); NOVA (NEJM 2016)",
    },
    {
        "drug_id": "niraparib",
        "gene_symbol": "BRCA2",
        "variant_ids": ["BRCA2_6174delT"],
        "genotype": "heterozygous",
        "phenotype": "germline BRCA2 pathogenic carrier",
        "recommendation": "FDA-approved for ovarian cancer maintenance "
        "(same as BRCA1).",
        "evidence_level": "A",
        "source": "FDA niraparib label; PRIMA; NOVA",
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
    # --- Olaparib / PALB2 (FDA 2023 expansion of PARPi biomarker panel) ---
    {
        "drug_id": "olaparib",
        "gene_symbol": "PALB2",
        "variant_ids": ["PALB2_1592delT", "PALB2_3113G_A"],
        "genotype": "heterozygous",
        "phenotype": "germline PALB2 pathogenic carrier",
        "recommendation": "PALB2 loss phenocopies BRCA2 loss and creates HR "
        "deficiency. Olaparib eligibility has been supported by NCCN "
        "guidelines and FDA biomarker expansion. Consider PARPi therapy "
        "alongside guideline-concordant management.",
        "evidence_level": "B",
        "source": "NCCN Breast v4.2024; Tung et al. JCO 2020",
    },
    # --- Capivasertib / AKT1 + PIK3CA + PTEN (FDA 2023, CAPItello-291) ---
    {
        "drug_id": "capivasertib",
        "gene_symbol": "AKT1",
        "variant_ids": ["AKT1_E17K"],
        "genotype": "heterozygous",
        "phenotype": "AKT1 E17K-mutated tumor",
        "recommendation": "FDA-approved indication. Capivasertib + "
        "fulvestrant in HR+/HER2- advanced breast cancer with an AKT1, "
        "PIK3CA, or PTEN alteration after endocrine progression.",
        "evidence_level": "A",
        "source": "FDA capivasertib label (CAPItello-291, NEJM 2023)",
    },
    {
        "drug_id": "capivasertib",
        "gene_symbol": "PIK3CA",
        "variant_ids": ["PIK3CA_H1047R", "PIK3CA_E545K"],
        "genotype": "heterozygous",
        "phenotype": "PIK3CA-altered tumor",
        "recommendation": "FDA-approved biomarker. Alpelisib is the longer-"
        "established PI3K-alpha-selective option for the same indication; "
        "capivasertib is often chosen when PI3K-alpha-specific toxicity "
        "(hyperglycemia, rash) is a concern.",
        "evidence_level": "A",
        "source": "FDA capivasertib label (CAPItello-291)",
    },
    # --- Elacestrant / ESR1 (FDA 2023, EMERALD) ---
    {
        "drug_id": "elacestrant",
        "gene_symbol": "ESR1",
        "variant_ids": ["ESR1_Y537S", "ESR1_D538G", "ESR1_Y537N", "ESR1_L536P"],
        "genotype": "any",
        "phenotype": "ESR1-mutated tumor",
        "recommendation": "FDA-approved indication. Elacestrant is approved "
        "for ER+/HER2-, ESR1-mutated advanced breast cancer after at least "
        "one prior line of endocrine therapy.",
        "evidence_level": "A",
        "source": "FDA elacestrant label (EMERALD, NEJM 2022)",
    },
    # --- Trastuzumab deruxtecan / ERBB2 (HER2-low expansion) ---
    {
        "drug_id": "trastuzumab_deruxtecan",
        "gene_symbol": "ERBB2",
        "variant_ids": ["ERBB2_L755S", "ERBB2_V777L"],
        "genotype": "any",
        "phenotype": "HER2-expressing or HER2-mutant tumor",
        "recommendation": "FDA-approved for HER2-low (IHC 1+ or 2+/ISH-) "
        "metastatic disease and for classical HER2+ disease after prior "
        "anti-HER2 therapy. Active even at low HER2 protein levels thanks "
        "to the bystander effect of the deruxtecan payload.",
        "evidence_level": "A",
        "source": "FDA trastuzumab deruxtecan label (DESTINY-Breast04 / -06)",
    },
]


def rules_for_drug(drug_id: str) -> list[PGxRule]:
    return [r for r in PGX_RULES if r["drug_id"] == drug_id]


def variants_for_gene(gene_symbol: str) -> list[VariantEntry]:
    return [v for v in VARIANTS.values() if v["gene_symbol"] == gene_symbol]


def drugs_for_gene(gene_symbol: str) -> list[DrugEntry]:
    """Drugs where this gene is the primary target or the metabolizing gene.

    Used when a patient pastes a sequence for a gene that isn't in the
    currently-selected drug's pathway. We surface relevant alternatives
    instead of silently running a useless analysis.
    """
    return [
        d
        for d in DRUGS.values()
        if d["primary_target_gene"] == gene_symbol or d["metabolizing_gene"] == gene_symbol
    ]


def drug_related_genes(drug_id: str) -> set[str]:
    """Set of gene symbols clinically relevant to this drug.

    Includes the direct binding target, the metabolizing gene (if any), and
    any "context" genes (e.g. synthetic-lethality partners like BRCA1/2 for
    olaparib — the drug doesn't bind BRCA1 but its entire clinical rationale
    depends on BRCA status).
    """
    d = DRUGS.get(drug_id)
    if d is None:
        return set()
    out: set[str] = {d["primary_target_gene"]}
    if d["metabolizing_gene"]:
        out.add(d["metabolizing_gene"])
    for g in d.get("context_genes", []):
        out.add(g)
    return out


def drugs_for_gene_inclusive(gene_symbol: str) -> list[DrugEntry]:
    """Drugs where this gene is the target, metabolizer, OR a context gene."""
    return [
        d
        for d in DRUGS.values()
        if d["primary_target_gene"] == gene_symbol
        or d["metabolizing_gene"] == gene_symbol
        or gene_symbol in d.get("context_genes", [])
    ]


# --- Demo patients ---------------------------------------------------------
#
# Three preset patient profiles for the 2-minute walkthrough. Genotypes are
# constructed from public CPIC and PharmGKB reference alleles. No real patient
# data is used (the UI surfaces this disclosure prominently).
#
# Design notes:
#  - Patient A uses an empty `variants` list — *1/*1 for every metabolism gene
#    is the wild-type reference; our analyzer treats "no variants" as the
#    green-light case and emits a "standard dosing" headline.
#  - Patient B exercises the caution path (CYP2D6 poor metabolizer).
#  - Patient C exercises the clinically serious path (DPYD*2A heterozygous).


class DemoPatient(TypedDict):
    id: str
    name: str
    age: int
    persona_name: str   # first name used in patient-friendly narrative ("Maya")
    scenario: str
    indication: str
    # Tumor subtype so the UI + the future drug-relevance filter can reason
    # about it. Covers both breast (HR+/HER2-, HER2+, HER2-low, TNBC) and
    # ovarian (high-grade serous — the dominant subtype for BRCA+ patients).
    subtype: Literal[
        "HR+/HER2-",
        "HER2+",
        "HER2-low",
        "TNBC",
        "ovarian_HGSOC",
    ]
    drug_id: str
    medication_display: str  # e.g. "Olaparib (Lynparza)"
    status: str  # "expected" | "reduced" | "dose-adjustment" — maps to StatusBadge
    status_color: str  # "success" | "warning" | "info"
    genotype_summary: dict[str, str]
    variant_ids: list[str]
    zygosity_overrides: dict[str, str]
    narrative: str


DEMO_PATIENTS: list[DemoPatient] = [
    # Three preset patients covering the three major breast cancer subtypes
    # (triple-negative, hormone-receptor positive, HER2-positive) and the
    # three severity levels (benefit / caution / warning) so a 2-minute
    # demo shows each flavor of output.
    {
        "id": "maya",
        "name": "Maya's story",
        "persona_name": "Maya",
        "age": 41,
        "scenario": "A targeted therapy match. Genetics that make a specific drug eligible.",
        "indication": "Triple-negative breast cancer, germline BRCA1+",
        "subtype": "TNBC",
        "drug_id": "olaparib",
        "medication_display": "Olaparib (Lynparza)",
        "status": "expected",
        "status_color": "success",
        "genotype_summary": {
            "BRCA1": "c.181T>G (p.Cys61Gly) pathogenic",
            "BRCA2": "wild-type",
            "CYP2D6": "*1/*1 (normal)",
            "DPYD": "*1/*1 (normal)",
        },
        "variant_ids": ["BRCA1_C61G"],
        "zygosity_overrides": {"BRCA1_C61G": "heterozygous"},
        "narrative": "Maya's tumor is HR-negative, HER2-negative, and she "
        "carries a pathogenic BRCA1 variant. That makes her eligible for "
        "olaparib, a targeted therapy that exploits the DNA-repair defect "
        "BRCA1 causes in cancer cells.",
    },
    {
        "id": "diana",
        "name": "Diana's story",
        "persona_name": "Diana",
        "age": 52,
        "scenario": "A common case. A genetic variant reducing a drug's effectiveness, and the alternatives.",
        "indication": "ER+ / HER2- early breast cancer",
        "subtype": "HR+/HER2-",
        "drug_id": "tamoxifen",
        "medication_display": "Tamoxifen",
        "status": "reduced",
        "status_color": "warning",
        "genotype_summary": {
            "CYP2D6": "*4/*4 (poor metabolizer)",
            "BRCA1": "wild-type",
            "BRCA2": "wild-type",
            "PIK3CA": "wild-type",
        },
        "variant_ids": ["CYP2D6_star4"],
        "zygosity_overrides": {"CYP2D6_star4": "homozygous"},
        "narrative": "Tamoxifen is a prodrug. CYP2D6 must convert it to its "
        "active form, and Diana's CYP2D6 works slowly. Her oncologist may "
        "consider an aromatase inhibitor instead.",
    },
    {
        "id": "priya",
        "name": "Priya's story",
        "persona_name": "Priya",
        "age": 58,
        "scenario": "HR deficiency in a different cancer. Same biology, different tumor.",
        "indication": "High-grade serous ovarian cancer, germline BRCA2+",
        "subtype": "ovarian_HGSOC",
        "drug_id": "niraparib",
        "medication_display": "Niraparib (Zejula)",
        "status": "expected",
        "status_color": "success",
        "genotype_summary": {
            "BRCA2": "c.5946delT pathogenic",
            "BRCA1": "wild-type",
            "PALB2": "wild-type",
            "CYP2D6": "*1/*1 (normal)",
        },
        "variant_ids": ["BRCA2_6174delT"],
        "zygosity_overrides": {"BRCA2_6174delT": "heterozygous"},
        "narrative": "Priya has advanced high-grade serous ovarian cancer and "
        "a germline BRCA2 pathogenic variant. Her tumor is HR-deficient, "
        "which is the same biology that makes Maya's tumor PARP-inhibitor "
        "sensitive. In the ovarian setting, niraparib is FDA-approved as "
        "first-line maintenance after platinum response, and olaparib is "
        "approved for BRCA-mutated maintenance (SOLO-1).",
    },
]


DEMO_NOTE = (
    "Demo patient genotypes constructed from public CPIC and PharmGKB "
    "reference alleles. No real patient data is used."
)
