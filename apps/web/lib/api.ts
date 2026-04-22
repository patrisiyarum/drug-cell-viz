import type {
  JobCreate,
  JobRead,
  MolecularResult,
  MorphologyResult,
} from "./types";
import type {
  AnalysisResult,
  Brca1Classification,
  BrcaExchangeRecord,
  Catalog,
  Demos,
  VariantInput,
} from "./bc-types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  createJob: (body: JobCreate) =>
    request<JobRead>("/api/jobs", { method: "POST", body: JSON.stringify(body) }),
  getJob: (id: string) => request<JobRead>(`/api/jobs/${id}`),
  getMolecular: (id: string) => request<MolecularResult>(`/api/molecular/${id}`),
  getMorphology: (id: string) => request<MorphologyResult>(`/api/morphology/${id}`),
  exportUrl: (jobId: string) => `${API_BASE}/api/export/${jobId}.zip`,

  // Breast cancer analysis flow
  getCatalog: () => request<Catalog>("/api/bc/catalog"),
  getDemos: () => request<Demos>("/api/bc/demos"),
  analyze: (body: { drug_id: string; variants: VariantInput[] }) =>
    request<AnalysisResult>("/api/bc/analyze", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  classifyBrca1: (hgvsProtein: string) =>
    request<Brca1Classification>("/api/brca1/classify", {
      method: "POST",
      body: JSON.stringify({ hgvs_protein: hgvsProtein }),
    }),
  lookupBrcaExchange: (hgvsProtein: string) =>
    request<BrcaExchangeRecord | null>(
      `/api/brca1/exchange?hgvs_protein=${encodeURIComponent(hgvsProtein)}`,
    ),

  // VCF: multipart upload → backend runs cyvcf2 ingest + full drug analysis.
  // Returns the same AnalysisResult shape used everywhere else, plus VCF-level
  // metadata (record counts, detected sample, per-catalog-variant detections).
  analyzeVcf: async (
    file: File,
    drugId: string,
  ): Promise<VcfAnalyzeResponse> => {
    const form = new FormData();
    form.append("file", file);
    const url = `${API_BASE}/api/vcf/analyze?drug_id=${encodeURIComponent(drugId)}`;
    const res = await fetch(url, { method: "POST", body: form });
    if (!res.ok) {
      throw new Error(`VCF analyze failed: ${res.status} ${await res.text()}`);
    }
    return (await res.json()) as VcfAnalyzeResponse;
  },

  /**
   * Virtual screening: rank a compound library against one HR-panel target.
   *
   * The backend uses RDKit docking + Morgan-fingerprint Tanimoto similarity
   * against a curated reference set, and returns candidates ranked by a
   * composite pocket_fit + chem_similarity score.
   */
  runScreening: (body: {
    target_gene: string;
    candidates: { id: string; name: string; smiles: string }[];
  }) =>
    request<ScreeningResponse>("/api/screening/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /**
   * Request the doctor-visit PDF for an analysis.
   *
   * The backend returns binary PDF; we hand it back as a Blob so the caller
   * can wire it into a download link or new-tab view.
   */
  downloadReportPdf: async (
    result: AnalysisResult,
    patientLabel?: string | null,
  ): Promise<Blob> => {
    const res = await fetch(`${API_BASE}/api/bc/report.pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result, patient_label: patientLabel ?? null }),
    });
    if (!res.ok) {
      throw new Error(`PDF failed: ${res.status} ${await res.text()}`);
    }
    return res.blob();
  },
};

export interface VcfDetectionDTO {
  catalog_id: string;
  gene: string;
  display_name: string;
  chrom: string;
  pos: number;
  ref: string;
  alt: string;
  zygosity: "heterozygous" | "homozygous";
  sample: string;
  vcf_filter: string;
}

export interface VcfAnalyzeResponse {
  total_records: number;
  records_pass: number;
  samples: string[];
  analyzed_sample: string;
  detections: VcfDetectionDTO[];
  novel_brca1_missense: string[];
  analysis: AnalysisResult | null;
}

export interface CandidateScore {
  candidate_id: string;
  name: string;
  smiles: string;
  pocket_fit: number;
  chem_similarity: number;
  closest_reference: string | null;
  fit_score: number;
  heavy_atom_count: number;
  pose_pdb_url: string | null;
  rank: number;
}

export interface ScreeningResponse {
  target_gene: string;
  target_uniprot: string;
  pocket_radius_angstrom: number;
  reference_binders: string[];
  protein_pdb_url: string;
  ranked: CandidateScore[];
}
