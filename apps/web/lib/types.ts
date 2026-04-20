// Hand-written mirror of the API schema. Replace with the output of
// `scripts/generate_ts_types.sh` once the Python environment is set up.

export type JobKind = "molecular" | "morphology" | "combined";
export type JobStatus = "pending" | "running" | "completed" | "failed";

export interface JobCreate {
  smiles: string;
  uniprot_id: string;
  kind?: JobKind;
}

export interface JobRead {
  id: string;
  kind: JobKind;
  status: JobStatus;
  smiles: string;
  uniprot_id: string;
  created_at: string;
  updated_at: string;
  error: string | null;
  molecular_result_id: string | null;
  morphology_result_id: string | null;
}

export interface DockingPose {
  rank: number;
  confidence: number;
  affinity_kcal_mol: number | null;
  pdb_url: string;
}

export interface MolecularResult {
  id: string;
  uniprot_id: string;
  smiles: string;
  protein_pdb_url: string;
  poses: DockingPose[];
  source: "alphafold_db" | "alphafold2_colabfold" | "pdb";
}

export interface MorphologyMatch {
  rank: number;
  similarity: number;
  compound_name: string | null;
  broad_sample_id: string;
  image_url: string;
  channel_urls: Record<string, string> | null;
  cell_line: string;
  perturbation_dose_um: number | null;
}

export interface MorphologyResult {
  id: string;
  smiles: string;
  query_fingerprint: string;
  matches: MorphologyMatch[];
  control_url: string;
}
