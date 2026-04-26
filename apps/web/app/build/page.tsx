"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, FileUp } from "lucide-react";

import {
  DrugPickerSection,
  RunAnalysisButton,
  VariantPickerSection,
  useBCAnalysisForm,
} from "@/components/BCAnalysisForm";
import { ResultsReport } from "@/components/ResultsReport";
import { api, type CtScanResponse } from "@/lib/api";
import type { AnalysisResult, VariantInput, Zygosity } from "@/lib/bc-types";
import {
  countSupportedSnps,
  detectionsToVariantInputs,
  parse23andMe,
  type Detection,
  type ParseResult,
} from "@/lib/twenty-three-and-me";

interface SelectedVariant {
  catalog_id: string;
  zygosity: Zygosity;
}

export default function BuildPage() {
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [lastContext, setLastContext] = useState<
    { drugId: string; variants: VariantInput[] } | null
  >(null);
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState<string | null>(null);

  const [uploadDetected, setUploadDetected] = useState<SelectedVariant[]>([]);
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);

  // Auto-scroll into view when a new result lands so the user doesn't have to
  // hunt for the report after clicking "Show me how this affects me."
  const resultsRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (result && resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [result?.id]);

  // Shared form state: DrugPickerSection and VariantPickerSection both read and
  // write this. Lives at the page level so the Step 1 and Step 3 cards stay in
  // sync.
  const form = useBCAnalysisForm({
    onResult: (r, ctx) => {
      setResult(r);
      setLastContext(ctx);
    },
    drugIdOverride: lastContext?.drugId,
    presetVariants: uploadDetected,
  });

  async function onSwitchDrug(newDrugId: string) {
    if (!lastContext) return;
    setSwitching(true);
    setSwitchError(null);
    try {
      const next = await api.analyze({
        drug_id: newDrugId,
        variants: lastContext.variants,
      });
      setResult(next);
      setLastContext({ drugId: newDrugId, variants: lastContext.variants });
    } catch (err) {
      setSwitchError(err instanceof Error ? err.message : "switch failed");
    } finally {
      setSwitching(false);
    }
  }

  function onDetected(parsed: ParseResult) {
    setParseResult(parsed);
    const variants = detectionsToVariantInputs(parsed.detectedVariants);
    setUploadDetected(
      variants
        .filter((v): v is { catalog_id: string; zygosity: Zygosity } =>
          Boolean(v.catalog_id),
        )
        .map((v) => ({ catalog_id: v.catalog_id, zygosity: v.zygosity })),
    );
  }

  return (
    <div className="flex flex-col bg-white">
      <header className="border-b bg-card">
        <div className="max-w-[1600px] mx-auto px-6 md:px-8 py-5 flex items-center justify-between gap-4">
          <Link href="/" className="text-muted-foreground hover:text-foreground text-sm">
            ← Back
          </Link>
          <Link href="/demo" className="text-sm text-primary hover:underline">
            Or pick a preset case
          </Link>
        </div>
      </header>

      <main className="flex-1 px-6 md:px-8 py-12 md:py-16">
        <div className="max-w-3xl mx-auto space-y-6">
          <div className="space-y-2 text-center">
            <h1 className="text-3xl md:text-4xl font-semibold">
              See how a medication might affect you
            </h1>
            <p className="text-muted-foreground text-base leading-relaxed max-w-2xl mx-auto">
              Pick a drug, optionally upload your data, and select the
              variants you know about. Your report will appear below.
            </p>
          </div>

          <StepCard n={1} title="Pick a medication">
            <DrugPickerSection form={form} />
          </StepCard>

          <StepCard
            n={2}
            title="Upload your data"
            subtitle="Optional. Skip if you already know which variants to pick."
          >
            <div className="space-y-4">
              <UploadCard
                onDetected={onDetected}
                parseResult={parseResult}
                onClear={() => {
                  setUploadDetected([]);
                  setParseResult(null);
                }}
              />
              <VcfUploadCard
                drugId={form.drugId}
                onResult={(r, drugId) => {
                  setResult(r);
                  setLastContext({ drugId, variants: [] });
                }}
              />
              <CtScanUploadCard
                onResult={() => {
                  /* the card renders its own preprocessing summary inline;
                     no state needs to flow up to the analyze call */
                }}
              />
            </div>
          </StepCard>

          <StepCard n={3} title="Select your variants">
            <div className="space-y-5">
              <VariantPickerSection form={form} />
              <div className="pt-2 border-t">
                <RunAnalysisButton form={form} />
              </div>
            </div>
          </StepCard>

          {switching ? (
            <div className="text-sm text-muted-foreground text-center">
              Re-running with the new drug…
            </div>
          ) : null}
          {switchError ? (
            <div className="text-sm text-red-600 text-center">{switchError}</div>
          ) : null}
        </div>

        {result ? (
          <div
            ref={resultsRef}
            className="max-w-[1600px] mx-auto mt-10 md:mt-14 scroll-mt-6"
          >
            <ResultsReport result={result} onSwitchDrug={onSwitchDrug} />
          </div>
        ) : null}
      </main>
    </div>
  );
}

/**
 * A numbered step wrapper: big primary-colored badge on the left, title on
 * the right, content below. Matches the visual rhythm of the results-page
 * cards (rounded-2xl border, p-5/p-6).
 */
function StepCard({
  n,
  title,
  subtitle,
  children,
}: {
  n: number;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-card border rounded-2xl p-5 md:p-6 space-y-4">
      <div className="flex items-start gap-3">
        <StepNumber n={n} />
        <div className="flex-1">
          <h2 className="text-lg md:text-xl font-semibold">{title}</h2>
          {subtitle ? (
            <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
          ) : null}
        </div>
      </div>
      <div>{children}</div>
    </section>
  );
}

function StepNumber({ n }: { n: number }) {
  return (
    <span className="w-7 h-7 flex-shrink-0 rounded-full bg-primary text-primary-foreground text-sm font-semibold flex items-center justify-center">
      {n}
    </span>
  );
}

function UploadCard({
  onDetected,
  parseResult,
  onClear,
}: {
  onDetected: (parsed: ParseResult) => void;
  parseResult: ParseResult | null;
  onClear: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [parsing, setParsing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  async function onFile(ev: React.ChangeEvent<HTMLInputElement>) {
    const file = ev.target.files?.[0];
    if (!file) return;
    setParsing(true);
    setErr(null);
    try {
      const text = await file.text();
      const parsed = parse23andMe(text);
      if (parsed.validCalls < 100) {
        throw new Error(
          "That doesn't look like a 23andMe raw data file. Upload the .txt export, not the PDF report.",
        );
      }
      onDetected(parsed);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "couldn't read the file");
    } finally {
      setParsing(false);
    }
  }

  return (
    <details className="bg-card border rounded-2xl overflow-hidden group">
      <summary className="cursor-pointer px-5 md:px-6 py-4 flex items-center gap-3 hover:bg-muted/40 transition-colors list-none">
        <span className="w-6 h-6 rounded-full bg-primary text-primary-foreground text-xs font-semibold flex items-center justify-center flex-shrink-0">
          A
        </span>
        <div className="flex-1">
          <div className="font-medium">23andMe raw data</div>
        </div>
        <span className="text-xs text-muted-foreground group-open:hidden">
          (optional)
        </span>
      </summary>
      <div className="border-t px-5 md:px-6 py-5 space-y-4">
        <input
          ref={inputRef}
          type="file"
          accept=".txt,.tsv,text/plain,text/tab-separated-values"
          onChange={onFile}
          className="sr-only"
        />
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragActive(false);
            if (e.dataTransfer.files[0] && inputRef.current) {
              inputRef.current.files = e.dataTransfer.files;
              inputRef.current.dispatchEvent(new Event("change", { bubbles: true }));
            }
          }}
          className={`border-2 border-dashed rounded-xl p-5 text-center transition-colors ${
            dragActive ? "border-primary bg-primary/5" : "border-slate-300 bg-slate-50"
          }`}
        >
          <FileUp className="w-7 h-7 mx-auto text-muted-foreground" aria-hidden />
          <p className="mt-2 text-sm text-gray-700">
            Drop your 23andMe raw data file here, or click to pick it.
          </p>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={parsing}
            className="mt-3 px-5 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 disabled:opacity-50"
          >
            {parsing ? "Reading…" : "Choose file"}
          </button>
        </div>

        {err ? <div className="text-sm text-red-600">{err}</div> : null}
        {parseResult ? <ParseSummary parsed={parseResult} onClear={onClear} /> : null}
      </div>
    </details>
  );
}

function ParseSummary({
  parsed,
  onClear,
}: {
  parsed: ParseResult;
  onClear: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2">
        <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0 mt-0.5" aria-hidden />
        <div className="text-sm flex-1">
          <span className="font-medium">File read.</span>{" "}
          <span className="text-muted-foreground">
            Matched <strong>{parsed.detectedVariants.length} of{" "}
            {countSupportedSnps()}</strong> clinically actionable CYP2D6 / DPYD
            SNPs in your file (scanned {parsed.validCalls.toLocaleString()}{" "}
            genotype calls).
          </span>
        </div>
        <button
          onClick={onClear}
          className="text-xs text-muted-foreground hover:text-foreground underline"
          type="button"
        >
          Clear
        </button>
      </div>
      {parsed.detectedVariants.length > 0 ? (
        <ul className="space-y-1">
          {parsed.detectedVariants.map((d) => (
            <li key={d.rsid} className="text-xs border rounded p-2 bg-white">
              <span className="font-medium">{d.displayName}</span>
              <span className="text-muted-foreground">
                {" "}
                · {d.gene} ·{" "}
                {d.copiesOfRiskAllele === 2 ? "both copies" : "one copy"} ·{" "}
                pre-selected below
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export type { Detection };


/**
 * VCF upload card. Mirrors the 23andMe uploader but targets clinical-grade
 * VCFs and calls /api/vcf/analyze on the server (cyvcf2 runtime). The whole
 * analysis comes back in one shot, including the detected variant list and
 * the full AnalysisResult.
 */
/**
 * The drug comes from Step 1's shared form state — we don't ask again here.
 */
function VcfUploadCard({
  drugId,
  onResult,
}: {
  drugId: string;
  onResult: (result: AnalysisResult, drugId: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [parsing, setParsing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [lastResp, setLastResp] = useState<{
    total: number;
    pass: number;
    sample: string;
    detections: number;
  } | null>(null);

  async function onFile(ev: React.ChangeEvent<HTMLInputElement>) {
    const file = ev.target.files?.[0];
    if (!file) return;
    setParsing(true);
    setErr(null);
    try {
      const resp = await api.analyzeVcf(file, drugId);
      setLastResp({
        total: resp.total_records,
        pass: resp.records_pass,
        sample: resp.analyzed_sample,
        detections: resp.detections.length,
      });
      if (resp.analysis) {
        onResult(resp.analysis, drugId);
      } else if (resp.detections.length === 0) {
        setErr(
          "No catalog variants detected in this VCF. Try a different drug or check that your VCF uses hg38 coordinates.",
        );
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "VCF upload failed");
    } finally {
      setParsing(false);
    }
  }

  return (
    <details className="bg-card border rounded-2xl overflow-hidden group">
      <summary className="cursor-pointer px-5 md:px-6 py-4 flex items-center gap-3 hover:bg-muted/40 transition-colors list-none">
        <span className="w-6 h-6 rounded-full bg-primary text-primary-foreground text-xs font-semibold flex items-center justify-center flex-shrink-0">
          B
        </span>
        <div className="flex-1">
          <div className="font-medium">Clinical VCF</div>
        </div>
        <span className="text-xs text-muted-foreground group-open:hidden">
          (optional)
        </span>
      </summary>
      <div className="border-t px-5 md:px-6 py-5 space-y-4">
        <input
          ref={inputRef}
          type="file"
          accept=".vcf,.vcf.gz,application/gzip,text/plain"
          onChange={onFile}
          className="sr-only"
        />
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragActive(false);
            if (e.dataTransfer.files[0] && inputRef.current) {
              inputRef.current.files = e.dataTransfer.files;
              inputRef.current.dispatchEvent(new Event("change", { bubbles: true }));
            }
          }}
          className={`border-2 border-dashed rounded-xl p-5 text-center transition-colors ${
            dragActive ? "border-primary bg-primary/5" : "border-slate-300 bg-slate-50"
          }`}
        >
          <FileUp className="w-7 h-7 mx-auto text-muted-foreground" aria-hidden />
          <p className="mt-2 text-sm text-gray-700">
            Drop your VCF file here, or click to pick it.
          </p>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={parsing}
            className="mt-3 px-5 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 disabled:opacity-50"
          >
            {parsing ? "Analyzing…" : "Choose file"}
          </button>
        </div>

        {err ? <div className="text-sm text-red-600">{err}</div> : null}
        {lastResp ? (
          <div className="text-sm bg-green-50 border border-green-200 rounded-lg p-3">
            Read <span className="font-mono">{lastResp.total}</span> records
            (<span className="font-mono">{lastResp.pass}</span> PASS) from
            sample <span className="font-mono">{lastResp.sample}</span>. Matched{" "}
            <span className="font-mono">{lastResp.detections}</span> catalog
            variant{lastResp.detections === 1 ? "" : "s"}. Full report below.
          </div>
        ) : null}
      </div>
    </details>
  );
}

/**
 * Radiogenomics CT-scan uploader — accepts a DICOM zip or NIfTI file, sends
 * it to /api/radiogenomics/upload, and renders the preprocessing metadata
 * and HRD probability that comes back. The backend's current prediction is
 * a placeholder (`label: "model_not_trained"`); this card surfaces the
 * preprocessing output honestly and tags the prediction as research-tier
 * via the response's `model_available` flag.
 */
function CtScanUploadCard({
  onResult,
}: {
  onResult: (r: CtScanResponse) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [parsing, setParsing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [lastResp, setLastResp] = useState<CtScanResponse | null>(null);

  async function onFile(ev: React.ChangeEvent<HTMLInputElement>) {
    const file = ev.target.files?.[0];
    if (!file) return;
    setParsing(true);
    setErr(null);
    try {
      const resp = await api.uploadCtScan(file);
      setLastResp(resp);
      onResult(resp);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "CT upload failed");
    } finally {
      setParsing(false);
    }
  }

  return (
    <details className="bg-card border rounded-2xl overflow-hidden group">
      <summary className="cursor-pointer px-5 md:px-6 py-4 flex items-center gap-3 hover:bg-muted/40 transition-colors list-none">
        <span className="w-6 h-6 rounded-full bg-primary text-primary-foreground text-xs font-semibold flex items-center justify-center flex-shrink-0">
          C
        </span>
        <div className="flex-1">
          <div className="font-medium flex items-center gap-2">
            CT scan
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 uppercase tracking-wide font-semibold">
              research
            </span>
          </div>
        </div>
        <span className="text-xs text-muted-foreground group-open:hidden">
          (optional)
        </span>
      </summary>
      <div className="border-t px-5 md:px-6 py-5 space-y-4">
        <p className="text-xs text-muted-foreground leading-relaxed">
          DICOM .zip or NIfTI (.nii / .nii.gz). Research-tier model from{" "}
          <a
            href="https://github.com/patrisiyarum/hrd-radiogenomics"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            hrd-radiogenomics
          </a>
          .
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".zip,.nii,.nii.gz,.tcia,application/zip,application/gzip"
          onChange={onFile}
          className="sr-only"
        />
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragActive(false);
            if (e.dataTransfer.files[0] && inputRef.current) {
              inputRef.current.files = e.dataTransfer.files;
              inputRef.current.dispatchEvent(new Event("change", { bubbles: true }));
            }
          }}
          className={`border-2 border-dashed rounded-xl p-5 text-center transition-colors ${
            dragActive ? "border-primary bg-primary/5" : "border-slate-300 bg-slate-50"
          }`}
        >
          <FileUp className="w-7 h-7 mx-auto text-muted-foreground" aria-hidden />
          <p className="mt-2 text-sm text-gray-700">
            Drop your CT scan here, or click to pick it.
          </p>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={parsing}
            className="mt-3 px-5 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 disabled:opacity-50"
          >
            {parsing ? "Analyzing…" : "Choose file"}
          </button>
        </div>

        {err ? <div className="text-sm text-red-600">{err}</div> : null}
        {lastResp ? <CtScanSummary resp={lastResp} /> : null}
      </div>
    </details>
  );
}

function CtScanSummary({ resp }: { resp: CtScanResponse }) {
  // Upload card only confirms the file was preprocessed cleanly. The HRD
  // prediction surfaces later, alongside the variant analysis, in the
  // ResultsReport's HrdCard radiogenomics panel — duplicating it here was
  // confusing because the upload step came before the model run from the
  // user's point of view.
  const shape = resp.metadata.original_shape.join(" × ");
  return (
    <div className="space-y-3">
      <div className="text-sm bg-green-50 border border-green-200 rounded-lg p-3 space-y-1">
        <div>
          <span className="font-medium">Preprocessed.</span>{" "}
          <span className="text-muted-foreground">
            Loaded a {resp.metadata.modality} volume of shape{" "}
            <span className="font-mono">{shape}</span> voxels and resampled to{" "}
            <span className="font-mono">
              {resp.metadata.target_shape.join(" × ")}
            </span>{" "}
            for the CNN input.
          </span>
        </div>
      </div>
    </div>
  );
}
