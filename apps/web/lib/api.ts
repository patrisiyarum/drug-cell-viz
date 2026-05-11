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

export interface DrugSummary {
  generic: string;
  brand: string | null;
  /** One-line plain-English indication summary from the FDA label. */
  indication: string;
}

/**
 * Response from the variant-evidence agent. Mirrors the FastAPI
 * `VariantEvidenceResponse` model exactly.
 */
export interface VariantEvidenceResponse {
  gene: string;
  hgvs_protein: string;
  indication: string | null;
  /** 2-3 sentence Claude-synthesized pathogenicity summary. The frontend
   * renders this as a paragraph above the drug list. */
  pathogenicity: string;
  /** Structured drug list — one entry per FDA-approved drug returned by
   * OpenFDA. Frontend renders as a bulleted list, one per line. */
  drugs: DrugSummary[];
  /** Optional one-sentence allele-frequency claim from gnomAD. Null if
   * gnomAD didn't return useful data. */
  rarity: string | null;
  /** Flat-text rendering of pathogenicity + drugs + rarity. Used by the
   * PDF generator and any non-UI consumer. */
  summary: string;
  /** Model name used for synthesis, e.g. "claude-sonnet-4-5-20250929"
   * or "stub" if the key was missing or parsing failed. */
  model: string;
  /** Raw structured output from each tool call, keyed by source. */
  evidence: {
    clinvar: Record<string, unknown> | null;
    openfda: Record<string, unknown> | null;
    gnomad: Record<string, unknown> | null;
  };
  tool_calls_succeeded: string[];
  tool_calls_attempted: string[];
  duration_ms: number;
  /** Disclosure that the synthesis step was constrained to formatting,
   * not invention. Surface this to the user so they can audit. */
  constrained: string;
}

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

  /**
   * LangGraph agent that pulls evidence for a variant from three public
   * databases (ClinVar, OpenFDA, gnomAD) in parallel and asks
   * Claude to format the retrieved evidence into a clinician-readable
   * summary. The synthesis prompt is constrained to *describing* the
   * evidence dict, not generating new medical claims.
   */
  variantEvidence: (gene: string, variant: string, indication?: string | null) =>
    request<VariantEvidenceResponse>("/api/agent/variant-evidence", {
      method: "POST",
      body: JSON.stringify({ gene, variant, indication: indication ?? null }),
    }),

  /**
   * Conversational walkthrough agent. Multi-turn — the frontend keeps
   * the full message history and re-sends it on every turn. The
   * `context` is the structured analysis result + indication, forwarded
   * into Claude's system prompt so the model can reason about the
   * patient's actual data and call the web_search tool when it needs
   * to ground something on a current source.
   */
  walkthroughChat: (
    messages: { role: "user" | "assistant"; content: string }[],
    context: Record<string, unknown>,
  ) =>
    request<WalkthroughResponse>("/api/agent/walkthrough", {
      method: "POST",
      body: JSON.stringify({ messages, context }),
    }),
  lookupBrcaExchange: (hgvsProtein: string) =>
    request<BrcaExchangeRecord | null>(
      `/api/brca1/exchange?hgvs_protein=${encodeURIComponent(hgvsProtein)}`,
    ),

  /**
   * Upload a CT scan (DICOM zip or NIfTI) for radiogenomics HRD prediction.
   *
   * The preprocessing pipeline (load → crop → resample to 96^3 → HU-window
   * normalise) is real; the prediction is a stub until the trained model
   * from the hrd-radiogenomics research repo is wired up. `model_available`
   * on the response tells the UI which banner to show.
   */
  uploadCtScan: async (file: File): Promise<CtScanResponse> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/api/radiogenomics/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      throw new Error(`CT upload failed: ${res.status} ${await res.text()}`);
    }
    return (await res.json()) as CtScanResponse;
  },

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
   * Score tumor-level HRD-LOH / LST / NTAI feature counts into the
   * Myriad-style three-tier label. Feature counts typically come from a
   * clinical lab report (myChoice, FoundationOne CDx) or from the
   * pangenome-graph SV pipeline in `pipelines/rules/genome_graph_sv.smk`.
   */
  scoreHrdScars: (body: { loh: number; lst: number; ntai: number }) =>
    request<HrdScarResponse>("/api/hrd/scars", {
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

  /**
   * HRDetect — score a VCF upload through the demo signature stub +
   * the published HRDetect logistic regression. Honest about the stub
   * extraction step (real signature deconvolution requires whole-genome
   * sequencing, not panel data); the frontend tile surfaces the
   * caveats array verbatim so the user knows what's real and what's
   * approximated.
   */
  scoreHrdetectVcf: async (file: File): Promise<HRDetectResponse> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${API_BASE}/api/hrdetect/score-vcf`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      throw new Error(`HRDetect failed: ${res.status} ${await res.text()}`);
    }
    return res.json() as Promise<HRDetectResponse>;
  },

  // ----- Patient profile -----

  getPatientProfile: (patientId: string) =>
    request<PatientFullProfile>(`/api/patients/${patientId}`),

  createPatient: (body: PatientCreate) =>
    request<PatientRead>("/api/patients", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  addMedication: (patientId: string, body: MedicationCreate) =>
    request<MedicationRead>(`/api/patients/${patientId}/medications`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteMedication: async (patientId: string, medId: number) => {
    const res = await fetch(
      `${API_BASE}/api/patients/${patientId}/medications/${medId}`,
      { method: "DELETE" },
    );
    if (!res.ok) throw new Error(`delete medication ${res.status}`);
  },

  addSymptom: (patientId: string, body: SymptomCreate) =>
    request<SymptomRead>(`/api/patients/${patientId}/symptoms`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteSymptom: async (patientId: string, sympId: number) => {
    const res = await fetch(
      `${API_BASE}/api/patients/${patientId}/symptoms/${sympId}`,
      { method: "DELETE" },
    );
    if (!res.ok) throw new Error(`delete symptom ${res.status}`);
  },

  addPatientUpload: (patientId: string, body: PatientUploadCreate) =>
    request<PatientUploadRead>(`/api/patients/${patientId}/uploads`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ----- Patient-profile types -----

export interface PatientRead {
  id: string;
  name: string;
  age: number;
  indication: string;
  drug_id: string | null;
  drug_name: string | null;
}

export interface HRDetectFeatures {
  hrd_loh: number;
  e_del_mh_prop: number;
  sbs3: number;
  sbs8: number;
  rs3: number;
  rs5: number;
}

export interface HRDetectResponse {
  probability: number;
  label: "predicted_hr_deficient" | "predicted_hr_proficient" | "uncertain";
  features: HRDetectFeatures;
  feature_source: "stub_extraction" | "user_provided";
  intercept: number;
  coefficients: Record<string, number>;
  duration_ms: number;
  caveats: string[];
}

export interface WalkthroughResponse {
  reply: string;
  citations: { url: string; title: string }[];
  model: string;
  duration_ms: number;
}

export interface PatientCreate {
  id: string;
  name: string;
  age: number;
  indication: string;
  drug_id?: string | null;
  drug_name?: string | null;
}

export interface MedicationRead {
  id: number;
  drug_name: string;
  dose: string | null;
  started_at: string | null;
  ended_at: string | null;
  notes: string | null;
}

export interface MedicationCreate {
  drug_name: string;
  dose?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  notes?: string | null;
}

export interface SymptomRead {
  id: number;
  occurred_on: string;
  label: string;
  severity: number;
  notes: string | null;
}

export interface SymptomCreate {
  occurred_on: string;
  label: string;
  severity: number;
  notes?: string | null;
}

export interface PatientUploadRead {
  id: number;
  upload_kind: "ct_scan" | "vcf" | "23andme" | "report";
  filename: string;
  asset_url: string | null;
  summary_json: string | null;
  uploaded_at: string;
}

export interface PatientUploadCreate {
  upload_kind: "ct_scan" | "vcf" | "23andme" | "report";
  filename: string;
  asset_url?: string | null;
  summary_json?: string | null;
}

export interface PatientFullProfile {
  patient: PatientRead;
  medications: MedicationRead[];
  symptoms: SymptomRead[];
  uploads: PatientUploadRead[];
}

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

export interface CtScanResponse {
  metadata: {
    modality: string;
    original_shape: [number, number, number];
    original_spacing_mm: [number, number, number];
    target_shape: [number, number, number];
    hu_window: [number, number];
  };
  hrd_probability: number;
  label: "predicted_hr_deficient" | "predicted_hr_proficient" | "uncertain" | "model_not_trained";
  confidence: "low" | "moderate" | "high" | "stub";
  caveats: string[];
  model_available: boolean;
  // Backend-served NIfTI URL for the resolved 3D volume. Set whenever the
  // server successfully assembled a volume (any input format); the
  // slideshow viewer prefers this over the original uploaded blob URL
  // because niivue can render NIfTI but not .tcia manifests or DICOM zips.
  volume_url?: string | null;
}

export interface HrdScarResponse {
  loh: number;
  lst: number;
  ntai: number;
  hrd_sum: number;
  label: "hr_deficient_scar" | "borderline_scar" | "hr_proficient_scar" | "insufficient";
  summary: string;
  interpretation: string;
  caveats: string[];
}

export interface ScreeningResponse {
  target_gene: string;
  target_uniprot: string;
  pocket_radius_angstrom: number;
  reference_binders: string[];
  protein_pdb_url: string;
  ranked: CandidateScore[];
}
