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

export interface CatalogGene {
  symbol: string;
  name: string;
  uniprot_id: string;
  role: string;
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
  disclaimers: string[];
  created_at: string;
}
