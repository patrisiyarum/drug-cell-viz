// Mirrors apps/api/src/api/services/bc_catalog.py + models/analysis.py

export type DrugCategory =
  | "hormone_therapy"
  | "her2_targeted"
  | "cdk46_inhibitor"
  | "parp_inhibitor"
  | "pi3k_inhibitor"
  | "chemotherapy"
  | "aromatase_inhibitor";

export interface CatalogDrug {
  id: string;
  name: string;
  category: DrugCategory;
  primary_target_gene: string;
  metabolizing_gene: string | null;
  mechanism: string;
  indication: string;
  supports_docking: boolean;
}

export type GeneEffectType =
  | "drug_target"
  | "drug_metabolism"
  | "dna_repair"
  | "other";

export interface CatalogGene {
  symbol: string;
  name: string;
  uniprot_id: string;
  role: string;
  plain_role: string;
  effect_type: GeneEffectType;
}

export type ClinicalSignificance =
  | "pathogenic"
  | "likely_pathogenic"
  | "uncertain"
  | "likely_benign"
  | "benign"
  | "drug_response";

export interface CatalogVariant {
  id: string;
  gene_symbol: string;
  name: string;
  hgvs_protein: string | null;
  residue_positions: number[];
  clinical_significance: ClinicalSignificance;
  effect_summary: string;
  plain_summary: string;
  effect_type: GeneEffectType;
}

export interface Catalog {
  drugs: CatalogDrug[];
  genes: CatalogGene[];
  variants: CatalogVariant[];
}

export type Zygosity = "heterozygous" | "homozygous";

export interface VariantInput {
  catalog_id?: string | null;
  gene_symbol?: string | null;
  protein_sequence?: string | null;
  zygosity: Zygosity;
}

export interface PGxVerdict {
  drug_name: string;
  gene_symbol: string;
  variant_label: string;
  zygosity: string;
  phenotype: string;
  recommendation: string;
  evidence_level: "A" | "B" | "C" | "D";
  source: string;
}

export interface PocketResidue {
  position: number;
  wildtype_aa: string | null;
  variant_aa: string | null;
  min_distance_to_ligand_angstrom: number | null;
  in_pocket: boolean;
}

export type HeadlineSeverity =
  | "info"
  | "caution"
  | "warning"
  | "contraindicated"
  | "benefit";

export interface GlossaryTerm {
  term: string;
  definition: string;
}

export interface HowWeKnow {
  source: string;
  link: string;
  summary: string;
}

export interface PlainLanguage {
  what_you_see: string;
  how_the_drug_works: string;
  what_it_means_for_you: string;
  next_steps: string;
  questions_to_ask: string[];
  how_we_know: HowWeKnow;
  glossary: GlossaryTerm[];
}

export interface SuggestedDrug {
  id: string;
  name: string;
  reason: string;
}

export interface AnalysisResult {
  id: string;
  drug_id: string;
  drug_name: string;
  target_gene: string;
  target_uniprot: string;
  protein_pdb_url: string;
  pose_pdb_url: string | null;
  pgx_verdicts: PGxVerdict[];
  pocket_residues: PocketResidue[];
  headline: string;
  headline_severity: HeadlineSeverity;
  plain_language: PlainLanguage;
  relevance_warning: string | null;
  suggested_drugs: SuggestedDrug[];
  classifiable_brca1_variants: string[];
  disclaimers: string[];
  created_at: string;
}

export interface DemoPatient {
  id: string;
  name: string;
  persona_name: string;
  age: number;
  scenario: string;
  indication: string;
  drug_id: string;
  medication_display: string;
  status: "expected" | "reduced" | "dose-adjustment";
  status_color: "success" | "warning" | "info";
  genotype_summary: Record<string, string>;
  variant_ids: string[];
  zygosity_overrides: Record<string, Zygosity>;
  narrative: string;
}

export interface Demos {
  note: string;
  patients: DemoPatient[];
}

// --- BRCA Exchange expert-panel lookup ---
export interface BrcaExchangeRecord {
  hgvs_cdna: string | null;
  hgvs_protein: string | null;
  enigma_classification: string | null;
  enigma_date_evaluated: string | null;
  enigma_method: string | null;
  clinvar_classification: string | null;
  sources: string | null;
  link: string | null;
}

// --- BRCA1 variant-effect classifier (Tier-3 ML model) ---

export type Brca1Label =
  | "likely_loss_of_function"
  | "likely_functional"
  | "uncertain";

export interface Brca1ComponentScores {
  xgb_probability: number;
  alphamissense_score: number | null;
  alphamissense_class: string | null;
  alphamissense_covered: boolean;
  alphamissense_value_used: number | null;
}

export interface Brca1Conformal {
  coverage: number;
  threshold: number;
  prediction_set: string[];
  label: "loss_of_function" | "functional" | "uncertain";
}

export interface Brca1Classification {
  hgvs_protein: string;
  ref_aa: string;
  position: number;
  alt_aa: string;
  consequence: string;
  domain: string;
  in_assayed_region: boolean;
  probability_loss_of_function: number;
  label: Brca1Label;
  confidence: "low" | "moderate" | "high";
  components: Brca1ComponentScores;
  conformal: Brca1Conformal;
  model_version: string;
  training_citation: string;
  holdout_auroc: number;
  holdout_auprc: number;
  caveats: string[];
}
