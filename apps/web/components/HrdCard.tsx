"use client";

import { useEffect, useState } from "react";
import {
  FlaskConical,
  Activity,
  Clock,
  Info,
  Scan,
  Microscope,
  ArrowRight,
  FileText,
} from "lucide-react";

import { Brca1FunctionCard } from "./Brca1FunctionCard";
import { api, type CtScanResponse, type HrdScarResponse } from "@/lib/api";
import type { AnalysisResult, HrdResult } from "@/lib/bc-types";

// Drugs in the PARP-inhibitor class. When the patient's current drug is one
// of these AND they have HR-deficient evidence, we surface a reversion-
// monitoring callout — a scar-based HRD score is historical (it records the
// tumor's past HR state), and ~20-30% of PARPi-treated BRCA-associated
// tumors develop reversion mutations that restore HR repair under drug
// pressure (Silverman & Schonhoft, Clin Cancer Res 2025). The Myriad scar
// cutoff of 42 doesn't see that reversion.
const PARP_INHIBITOR_DRUG_IDS = new Set([
  "olaparib",
  "niraparib",
  "rucaparib",
  "talazoparib",
]);

/**
 * Filenames of the patient's uploaded records that each lab experiment
 * reads from. Surfaced inside each LabTile so the patient can see which
 * file in their profile drives which experiment ("Reading: maya_brca1.vcf").
 * When a field is missing we fall back to a generic label.
 */
export interface RecordRefs {
  vcfFilename?: string | null;
  ctScanFilename?: string | null;
  reportFilename?: string | null;
}

interface Props {
  hrd: HrdResult;
  /**
   * BRCA1 variants the Tier-3 ML classifier can score (in HGVS protein
   * notation). When non-empty we render an opt-in subsection inside this
   * card so the ML prediction appears as part of the HR-deficiency story
   * rather than as a separate card further down the page.
   */
  classifiableBrca1Variants?: string[];
  /** Drug id the patient is on — used to gate the PARPi reversion callout. */
  drugId?: string | null;
  /**
   * Path to a CT-scan fixture (served from /public) or an upload URL that
   * the radiogenomics model should score. When provided, renders a
   * "Run radiogenomics model" panel inside this card so the CT prediction
   * lives with the other HR-deficiency evidence. null = no CT available
   * for this patient → panel hidden.
   */
  ctScanUrl?: string | null;
  /** Display label for the CT fixture, e.g. "Maya's pelvic CT". */
  ctScanLabel?: string | null;
  /**
   * Pre-filled tumor-scar numbers from a patient's myChoice / FoundationOne
   * CDx report (parsed upstream from the upload's summary text). When set,
   * the scar panel auto-runs against these values instead of waiting for
   * the user to type them in.
   */
  scarPrefill?: { loh: number; lst: number; ntai: number } | null;
  /** See RecordRefs above. */
  recordRefs?: RecordRefs;
  /**
   * Full analysis result. When provided, the tab strip renders a small
   * PDF-download button on the right side so the patient can grab the
   * doctor-visit report from the same surface as the tabs.
   */
  analysisResult?: AnalysisResult | null;
  /** Patient name for the PDF filename / header. */
  patientLabel?: string | null;
}

/**
 * HR-deficiency result, framed as a small science lab.
 *
 * Layout (refactored):
 *  1. Verdict hero — slim card with the label, score, one-liner, reversion
 *     callout (if applicable), and a single clear next-step CTA. No nested
 *     panels here — keeps it from feeling like a wall of text.
 *  2. "Your sample" — the patient's variants rendered as the input data the
 *     experiments below are reading. Visually distinct from the experiments
 *     so the patient can tell what's input vs. output.
 *  3. "The Lab" — up to three sibling tiles framed as independent
 *     experiments all answering the same question: is the tumor HR-deficient?
 *     The patient can see at a glance that these three lines of evidence
 *     converge (or diverge) on the same answer.
 *  4. Caveats expander — collapsed by default.
 *
 * The compact "indeterminate + no evidence" branch is kept for patients
 * whose finding actually isn't HR-deficiency (e.g. Diana's CYP2D6 case),
 * so we don't show three irrelevant lab tiles.
 */
export function HrdCard({
  hrd,
  classifiableBrca1Variants = [],
  drugId = null,
  ctScanUrl = null,
  ctScanLabel = null,
  scarPrefill = null,
  recordRefs = {},
  analysisResult = null,
  patientLabel = null,
}: Props) {
  const [tab, setTab] = useState<"result" | "lab">("result");
  const showReversionCallout =
    hrd.label === "hr_deficient" &&
    !!drugId &&
    PARP_INHIBITOR_DRUG_IDS.has(drugId);

  // Compact "not applicable" rendering for patients without HR-panel variants.
  // When a CT fixture is provided we still render the radiogenomics tile so
  // the patient sees that even a germline-clean result doesn't rule out an
  // HR-deficient tumor (somatic BRCA loss, BRCA1 promoter methylation, etc.).
  if (hrd.label === "indeterminate" && hrd.evidence.length === 0) {
    const indeterminateTiles: React.ReactNode[] = [];
    if (ctScanUrl) {
      indeterminateTiles.push(
        <LabTile
          key="ct"
          title="CT imaging model"
          tests="Predicts HR-deficiency from tumor texture in your scan."
          icon={<Scan className="w-4 h-4" aria-hidden />}
          recordLabel={
            recordRefs.ctScanFilename ?? ctScanLabel ?? "your CT scan"
          }
        >
          <RadiogenomicsCtPanelBody
            ctScanUrl={ctScanUrl}
            currentDrugId={drugId}
          />
        </LabTile>,
      );
    }

    return (
      <div className="space-y-4">
        {indeterminateTiles.length > 0 ? (
          <TabBar
            tab={tab}
            setTab={setTab}
            labTileCount={indeterminateTiles.length}
            analysisResult={analysisResult}
            patientLabel={patientLabel}
          />
        ) : null}

        {tab === "result" || indeterminateTiles.length === 0 ? (
          <section className="rounded-2xl border border-border bg-muted/40 p-5 text-sm space-y-2">
            <div className="flex items-baseline justify-between gap-3 flex-wrap">
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  HR-deficiency status
                </div>
                <div className="font-medium">Not detected from germline</div>
              </div>
              <span className="text-[11px] text-muted-foreground">
                Score 0 / 100
              </span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              None of your variants hit the HR-repair panel. About one in three
              HR-deficient ovarian tumors are still HRD via somatic events a
              germline panel can&apos;t see
              {ctScanUrl
                ? " — open the lab tab to run the imaging experiment from that angle."
                : " — a tumor sequencing test would be the next step."}
            </p>
          </section>
        ) : null}

        {tab === "lab" && indeterminateTiles.length > 0 ? (
          <LabSection
            tagline="Even with a clean germline panel, imaging can pick up HR-deficiency from somatic events."
            tiles={indeterminateTiles}
          />
        ) : null}
      </div>
    );
  }

  const style = {
    hr_deficient: {
      bg: "bg-success/10",
      border: "border-success/40",
      pill: "bg-success/20 text-success",
      label: "HR-deficient",
      oneLiner:
        "Tumor likely can't repair DNA breaks. PARP inhibitors may be an option.",
    },
    hr_proficient: {
      bg: "bg-muted",
      border: "border-border",
      pill: "bg-muted text-foreground",
      label: "HR-proficient",
      oneLiner:
        "Your HR-repair genes look intact. PARP inhibitors are unlikely to be prioritized unless tumor testing says otherwise.",
    },
    indeterminate: {
      bg: "bg-warning/10",
      border: "border-warning/40",
      pill: "bg-warning/20 text-warning",
      label: "Mixed signals",
      oneLiner:
        "Some HR-panel variants are present, but not enough to make a confident call. Worth discussing with your oncologist.",
    },
  }[hrd.label];

  const hideMl = classifiableBrca1Variants.length > 0;
  const variantEvidence = hideMl
    ? hrd.evidence.filter((e) => e.source !== "ml_prediction")
    : hrd.evidence;

  // Build the lab tiles dynamically so we only render experiments that
  // actually apply to this patient.
  const tiles: React.ReactNode[] = [];
  if (classifiableBrca1Variants.length > 0) {
    tiles.push(
      <LabTile
        key="ml"
        title="DNA-repair classifier"
        tests="Tests whether your variant breaks BRCA1's repair function."
        icon={<FlaskConical className="w-4 h-4" aria-hidden />}
        recordLabel={recordRefs.vcfFilename ?? "your VCF (genetic data)"}
      >
        <Brca1ClassifierBody hgvsList={classifiableBrca1Variants} />
      </LabTile>,
    );
  }
  if (ctScanUrl) {
    tiles.push(
      <LabTile
        key="ct"
        title="CT imaging model"
        tests="Predicts HR-deficiency from tumor texture in your scan."
        icon={<Scan className="w-4 h-4" aria-hidden />}
        recordLabel={
          recordRefs.ctScanFilename ?? ctScanLabel ?? "your CT scan"
        }
      >
        <RadiogenomicsCtPanelBody
          ctScanUrl={ctScanUrl}
          currentDrugId={drugId}
        />
      </LabTile>,
    );
  }
  if (hrd.label !== "hr_proficient") {
    tiles.push(
      <LabTile
        key="scar"
        title="Tumor scar score"
        tests="Counts permanent DNA scars left by past failed repair."
        icon={<Activity className="w-4 h-4" aria-hidden />}
        recordLabel={
          recordRefs.reportFilename ?? "your tumor scar report"
        }
      >
        <TumorScarBody prefill={scarPrefill} />
      </LabTile>,
    );
  }

  return (
    <div className="space-y-5">
      <TabBar
        tab={tab}
        setTab={setTab}
        labTileCount={tiles.length}
        analysisResult={analysisResult}
        patientLabel={patientLabel}
      />

      {tab === "result" ? (
        <div className="space-y-3">
          {/* 1. Verdict — wrapped in a SectionCard so it shares the same
              gold-seam + rounded-2xl border treatment as the rest of the
              Result-tab sections. The label-specific tint is now a slim
              top-of-card accent strip instead of a full background. */}
          <SectionCard label="HR-deficiency result">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <h3 className="text-xl md:text-2xl font-semibold">
                {style.label}
              </h3>
              <div
                className={`px-3 py-1.5 rounded-full text-sm font-semibold ${style.pill}`}
              >
                Score {hrd.score} / 100
              </div>
            </div>
            <p className="text-sm leading-relaxed">{style.oneLiner}</p>
            {showReversionCallout ? <ReversionAwarenessInfo /> : null}
            {hrd.label === "hr_deficient" ? (
              <NextStepBanner drugId={drugId} />
            ) : null}
          </SectionCard>

          {/* 2. Your sample — same SectionCard shell. */}
          {variantEvidence.length > 0 ? (
            <SectionCard label="Your sample">
              <p className="text-xs text-muted-foreground">
                What the lab is reading.
              </p>
              <div className="flex flex-wrap gap-2">
                {variantEvidence.map((e, i) => (
                  <div
                    key={i}
                    className="inline-flex items-baseline gap-2 rounded-lg border bg-white px-3 py-1.5 text-sm"
                  >
                    <span className="font-semibold">{e.gene}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {stripGenePrefix(e.variant_label, e.gene)}
                    </span>
                  </div>
                ))}
              </div>
            </SectionCard>
          ) : null}

          {/* 3. Caveats — same SectionCard, content is the bullet list. */}
          {hrd.caveats.length > 0 ? (
            <SectionCard label="Caveats">
              <ul className="space-y-1 list-disc pl-5 text-xs text-muted-foreground leading-relaxed">
                {hrd.caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </SectionCard>
          ) : null}
        </div>
      ) : null}

      {tab === "lab" && tiles.length > 0 ? (
        <LabSection
          tagline={`${tiles.length === 1 ? "One experiment" : `${tiles.length} independent experiments`} testing whether your tumor is HR-deficient. Each runs on a different record from your profile.`}
          tiles={tiles}
        />
      ) : null}
    </div>
  );
}

// ============================================================================
// Lab framing primitives
// ============================================================================

/**
 * Shared section shell for the Result tab. Same chrome as a LabTile —
 * gold seam at the top, rounded-2xl border, consistent inner padding —
 * so the verdict, "Your sample", and "Caveats" sections share visual
 * rhythm with each other and with the Lab tab.
 */
function SectionCard({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border bg-card overflow-hidden">
      <div className="h-px bg-gradient-to-r from-amber-400/40 via-amber-500 to-amber-400/40" />
      <div className="p-4 md:p-5 space-y-3">
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground font-semibold">
          {label}
        </div>
        {children}
      </div>
    </div>
  );
}

/**
 * Tab strip at the top of HrdCard — splits the verdict ("Result") from
 * the simulated experiments ("Lab"). Counter on the Lab tab tells the
 * patient how many experiments are queued up for them to run.
 */
function TabBar({
  tab,
  setTab,
  labTileCount,
  analysisResult,
  patientLabel,
}: {
  tab: "result" | "lab";
  setTab: (t: "result" | "lab") => void;
  labTileCount: number;
  analysisResult?: AnalysisResult | null;
  patientLabel?: string | null;
}) {
  const base =
    "px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px";
  return (
    <div className="border-b flex items-center gap-1">
      <button
        type="button"
        onClick={() => setTab("result")}
        className={`${base} ${
          tab === "result"
            ? "border-amber-500 text-foreground"
            : "border-transparent text-muted-foreground hover:text-foreground"
        }`}
      >
        Result
      </button>
      <button
        type="button"
        onClick={() => setTab("lab")}
        className={`${base} inline-flex items-center gap-2 ${
          tab === "lab"
            ? "border-amber-500 text-foreground"
            : "border-transparent text-muted-foreground hover:text-foreground"
        }`}
      >
        <Microscope className="w-3.5 h-3.5" aria-hidden />
        Lab
        {labTileCount > 0 ? (
          <span className="text-[11px] rounded-full bg-amber-100 text-amber-800 px-1.5 py-0.5 font-mono">
            {labTileCount}
          </span>
        ) : null}
      </button>
      {analysisResult ? (
        <div className="ml-auto pb-1 no-print">
          <PdfDownloadInline
            result={analysisResult}
            patientLabel={patientLabel ?? null}
          />
        </div>
      ) : null}
    </div>
  );
}

/**
 * Small "Download PDF" button shown on the right side of the TabBar so
 * the patient can grab the doctor-visit report without scrolling. Same
 * blob → object-URL flow as the old DoctorVisitPdfButton card.
 */
function PdfDownloadInline({
  result,
  patientLabel,
}: {
  result: AnalysisResult;
  patientLabel: string | null;
}) {
  const [downloading, setDownloading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onClick() {
    setDownloading(true);
    setErr(null);
    try {
      const blob = await api.downloadReportPdf(result, patientLabel);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pharmacogenomic-report-${result.drug_id}-${result.id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not generate PDF");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {err ? <span className="text-[11px] text-red-600">{err}</span> : null}
      <button
        type="button"
        onClick={onClick}
        disabled={downloading}
        className="inline-flex items-center gap-1.5 rounded-lg border bg-white px-3 py-1.5 text-xs font-medium hover:bg-amber-50 hover:border-amber-300 disabled:opacity-60 transition-colors"
        title="Download the doctor-visit report"
      >
        <FileText className="w-3.5 h-3.5" aria-hidden />
        {downloading ? "Generating…" : "Download PDF"}
      </button>
    </div>
  );
}

/**
 * Section wrapper for "The Lab" — the row of independent experiments. Has
 * its own header so the patient knows these tiles are siblings answering
 * the same question, not stacked findings.
 */
function LabSection({
  tagline,
  tiles,
}: {
  tagline: string;
  tiles: React.ReactNode[];
}) {
  return (
    <section className="space-y-3">
      <div className="space-y-1">
        <h4 className="text-base font-semibold flex items-center gap-2">
          <Microscope
            className="w-4 h-4 text-amber-500 flex-shrink-0"
            aria-hidden
          />
          Let&apos;s run your results in our simulated lab
        </h4>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {tagline}
        </p>
      </div>
      <div
        className={`grid gap-3 ${
          tiles.length >= 3
            ? "md:grid-cols-3"
            : tiles.length === 2
              ? "md:grid-cols-2"
              : "md:grid-cols-1"
        }`}
      >
        {tiles}
      </div>
    </section>
  );
}

/**
 * One experiment tile. Visually consistent across the three experiments so
 * they read as siblings: small icon + title, one-line "what this tests",
 * then the experiment-specific body (Run button + result).
 *
 * Subtle gold seam at the top is the Kintsugi visual hook — the lab is
 * where the cracks (variants) get repaired into something useful.
 */
function LabTile({
  title,
  tests,
  icon,
  recordLabel,
  children,
}: {
  title: string;
  tests: string;
  icon: React.ReactNode;
  /**
   * Filename (or descriptive label) of the patient record this experiment
   * reads from. Surfaces inside the tile so the patient can trace which
   * file in their profile drives which model output.
   */
  recordLabel?: string | null;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border bg-card overflow-hidden flex flex-col">
      <div className="h-px bg-gradient-to-r from-amber-400/40 via-amber-500 to-amber-400/40" />
      <div className="p-4 space-y-3 flex-1 flex flex-col">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <span className="text-primary flex-shrink-0">{icon}</span>
            {title}
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {tests}
          </p>
        </div>
        {recordLabel ? (
          <div className="rounded-md border border-dashed border-amber-300/70 bg-amber-50/40 px-2.5 py-1.5">
            <div className="text-[10px] uppercase tracking-wide text-amber-700/80 font-semibold">
              Reading record
            </div>
            <div
              className="text-xs font-mono text-foreground truncate"
              title={recordLabel}
            >
              {recordLabel}
            </div>
          </div>
        ) : null}
        <div className="flex-1 flex flex-col">{children}</div>
      </div>
    </div>
  );
}

/**
 * The "what to do with this result" CTA for HR-deficient patients.
 * If they're already on a PARP inhibitor, we point at reversion monitoring;
 * otherwise we point at the PARPi conversation.
 */
function NextStepBanner({ drugId }: { drugId: string | null }) {
  const onParpi = !!drugId && PARP_INHIBITOR_DRUG_IDS.has(drugId);
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50/70 p-3 flex items-start gap-3">
      <ArrowRight
        className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5"
        aria-hidden
      />
      <div className="text-sm leading-relaxed">
        <span className="font-semibold">Next step:</span>{" "}
        {onParpi
          ? "Ask your oncologist about serial ctDNA monitoring to catch reversion mutations early."
          : "Bring this report to your oncologist and ask whether a PARP inhibitor (olaparib, niraparib, or rucaparib) is right for you."}
      </div>
    </div>
  );
}

// ============================================================================
// Experiment bodies
// ============================================================================

/**
 * Tumor-scar score body — bare content (no outer card), so it slots inside
 * a LabTile cleanly. Same logic as before: auto-runs when prefill is set.
 */
function TumorScarBody({
  prefill,
}: {
  prefill?: { loh: number; lst: number; ntai: number } | null;
}) {
  const [loh, setLoh] = useState(prefill ? String(prefill.loh) : "");
  const [lst, setLst] = useState(prefill ? String(prefill.lst) : "");
  const [ntai, setNtai] = useState(prefill ? String(prefill.ntai) : "");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<HrdScarResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!prefill) return;
    setLoh(String(prefill.loh));
    setLst(String(prefill.lst));
    setNtai(String(prefill.ntai));
    let cancelled = false;
    (async () => {
      setRunning(true);
      try {
        const resp = await api.scoreHrdScars(prefill);
        if (!cancelled) setResult(resp);
      } catch (e) {
        if (!cancelled)
          setErr(e instanceof Error ? e.message : "scoring failed");
      } finally {
        if (!cancelled) setRunning(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill?.loh, prefill?.lst, prefill?.ntai]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setRunning(true);
    try {
      const resp = await api.scoreHrdScars({
        loh: Number(loh),
        lst: Number(lst),
        ntai: Number(ntai),
      });
      setResult(resp);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "scoring failed");
    } finally {
      setRunning(false);
    }
  }

  const labelStyles: Record<HrdScarResponse["label"], string> = {
    hr_deficient_scar: "text-success bg-success/10 border-success/40",
    borderline_scar: "text-warning bg-warning/10 border-warning/40",
    hr_proficient_scar: "text-muted-foreground bg-muted border-border",
    insufficient: "text-muted-foreground bg-muted border-border",
  };
  const labelText: Record<HrdScarResponse["label"], string> = {
    hr_deficient_scar: "HR-deficient",
    borderline_scar: "Borderline",
    hr_proficient_scar: "HR-proficient",
    insufficient: "Insufficient data",
  };

  return (
    <div className="space-y-3 flex-1 flex flex-col">
      <form onSubmit={onSubmit} className="space-y-2">
        <div className="flex flex-wrap gap-2">
          <LabeledNumber label="HRD-LOH" value={loh} onChange={setLoh} />
          <LabeledNumber label="LST" value={lst} onChange={setLst} />
          <LabeledNumber label="NTAI" value={ntai} onChange={setNtai} />
        </div>
        {/* When the scar numbers came from a stored report (Maya / Priya),
            the experiment auto-runs on mount — no need for a Run button.
            For /build users typing numbers manually, we keep the button
            so they can submit. Press Enter inside any input also works. */}
        {!prefill ? (
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={running || !loh || !lst || !ntai}
              className="inline-flex items-center justify-center rounded-lg bg-primary text-primary-foreground px-3 py-1.5 text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {running ? "Scoring…" : "Run"}
            </button>
          </div>
        ) : null}
      </form>
      <div className="flex-1 min-h-[5rem] flex flex-col justify-end">
        {err ? <p className="text-xs text-red-600">{err}</p> : null}
        {running && !result ? (
          <p className="text-xs text-muted-foreground italic">Scoring…</p>
        ) : null}
        {result ? (
          <div
            className={`rounded-lg border p-3 text-sm ${labelStyles[result.label]}`}
          >
            <div className="flex items-baseline justify-between gap-2 flex-wrap">
              <span className="font-semibold">{labelText[result.label]}</span>
              <span className="text-xs">
                HRD-sum {result.hrd_sum} / 100
              </span>
            </div>
            <details className="mt-2 text-xs">
              <summary className="cursor-pointer opacity-80 hover:opacity-100">
                Details
              </summary>
              <p className="mt-1 leading-relaxed">{result.summary}</p>
              <p className="mt-1 leading-relaxed">{result.interpretation}</p>
            </details>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function LabeledNumber({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="text-xs flex flex-col gap-0.5">
      <span className="font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <input
        type="number"
        min={0}
        inputMode="numeric"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-16 border rounded px-2 py-1 bg-white text-sm"
        placeholder="0"
      />
    </label>
  );
}

/**
 * Collapsible info button that surfaces the reversion-awareness caveat for
 * PARPi patients.
 */
function ReversionAwarenessInfo() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative inline-flex">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[11px] font-medium text-warning hover:bg-warning/20 transition-colors"
        aria-label="Reversion awareness info"
        aria-expanded={open}
      >
        <Info className="w-3 h-3" aria-hidden />
        Reversion awareness
      </button>
      {open ? (
        <div className="absolute left-0 top-7 z-30 w-80 rounded-xl border border-warning/40 bg-white p-4 shadow-xl text-sm leading-relaxed space-y-2">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide font-semibold text-warning">
            <Clock className="w-3.5 h-3.5" aria-hidden />
            Reversion awareness
          </div>
          <p>
            An HR-deficient result is <strong>historical</strong>. It describes
            the tumor&apos;s past DNA-repair state, not its current one.
          </p>
          <p className="text-muted-foreground">
            Roughly 20 to 30 percent of BRCA-associated tumors treated with a
            PARP inhibitor develop small &ldquo;reversion&rdquo; mutations that
            quietly restore the broken BRCA gene under drug pressure. When that
            happens the tumor is no longer HR-deficient, but the scar-based
            score on this card won&apos;t reflect it (the scars are permanent).
          </p>
          <p className="text-muted-foreground">
            If you&apos;ve been on a PARP inhibitor for six months or more, ask
            your oncologist about <strong>serial ctDNA testing</strong> to
            catch reversion mutations early.
          </p>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Radiogenomics CT body — bare content for a LabTile.
 */
function RadiogenomicsCtPanelBody({
  ctScanUrl,
  currentDrugId = null,
}: {
  ctScanUrl: string;
  currentDrugId?: string | null;
}) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<CtScanResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // Auto-run on mount so the CT tile reaches the same "result-shown" state
  // as the BRCA1 + scar tiles without an extra click. Same fetch + upload
  // flow as before — just triggered eagerly instead of on button press.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setRunning(true);
      try {
        const resp = await fetch(ctScanUrl);
        if (!resp.ok) throw new Error(`could not fetch ${ctScanUrl}`);
        const blob = await resp.blob();
        const name = ctScanUrl.split("/").pop() ?? "ct_scan.nii.gz";
        const file = new File([blob], name, { type: "application/gzip" });
        const out = await api.uploadCtScan(file);
        if (!cancelled) setResult(out);
      } catch (e) {
        if (!cancelled)
          setErr(e instanceof Error ? e.message : "CT upload failed");
      } finally {
        if (!cancelled) setRunning(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ctScanUrl]);

  return (
    <div className="flex-1 flex flex-col justify-end min-h-[5rem]">
      {err ? <p className="text-xs text-red-600">{err}</p> : null}
      {running && !result ? (
        <p className="text-xs text-muted-foreground italic">Running model…</p>
      ) : null}
      {result ? (
        <CtPredictionResult result={result} currentDrugId={currentDrugId} />
      ) : null}
    </div>
  );
}

function CtPredictionResult({
  result,
  currentDrugId,
}: {
  result: CtScanResponse;
  currentDrugId?: string | null;
}) {
  const labelText: Record<CtScanResponse["label"], string> = {
    predicted_hr_deficient: "Predicted HR-deficient",
    predicted_hr_proficient: "Predicted HR-proficient",
    uncertain: "Uncertain",
    model_not_trained: "Model not wired (stub)",
  };
  const labelStyles: Record<CtScanResponse["label"], string> = {
    predicted_hr_deficient: "text-success bg-success/10 border-success/40",
    predicted_hr_proficient: "text-muted-foreground bg-muted border-border",
    uncertain: "text-warning bg-warning/10 border-warning/40",
    model_not_trained: "text-muted-foreground bg-muted border-border",
  };

  const showParpCallout =
    result.label === "predicted_hr_deficient" &&
    !!currentDrugId &&
    !PARP_INHIBITOR_DRUG_IDS.has(currentDrugId);

  const pct = Math.round(result.hrd_probability * 100);

  return (
    <div className="space-y-3">
      <div
        className={`rounded-lg border p-3 text-sm ${labelStyles[result.label]}`}
      >
        <div className="flex items-baseline justify-between gap-2 flex-wrap">
          <span className="font-semibold">{labelText[result.label]}</span>
          <span className="text-xs">{pct}% p(HRD)</span>
        </div>
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer opacity-80 hover:opacity-100">
            Details
          </summary>
          <ul className="mt-1 space-y-1 list-disc pl-5 opacity-90">
            {result.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </details>
      </div>

      {showParpCallout ? (
        <ParpInhibitorActionCallout currentDrugId={currentDrugId} />
      ) : null}
    </div>
  );
}

function ParpInhibitorActionCallout({
  currentDrugId,
}: {
  currentDrugId: string;
}) {
  const isTamoxifen = currentDrugId === "tamoxifen";
  return (
    <div className="rounded-lg border-l-4 border-primary/60 bg-primary/5 p-3 space-y-1.5 text-xs leading-relaxed">
      <div className="flex items-center gap-2 uppercase tracking-wide font-semibold text-primary text-[10px]">
        <Info className="w-3 h-3" aria-hidden />
        Ask your oncologist about
      </div>
      <ol className="list-decimal pl-4 space-y-0.5">
        <li>A tumor-sequencing test (Myriad myChoice or FoundationOne CDx).</li>
        <li>
          PARP-inhibitor eligibility instead of{" "}
          {isTamoxifen ? "tamoxifen alone" : "the current regimen alone"}.
        </li>
      </ol>
    </div>
  );
}

function stripGenePrefix(label: string, gene: string): string {
  const prefix = `${gene} `;
  return label.startsWith(prefix) ? label.slice(prefix.length) : label;
}

/**
 * BRCA1 classifier body for a LabTile. Renders the existing
 * Brca1FunctionCard (which already has its own internal layout) without
 * any extra wrapping — the LabTile is the wrapper now.
 */
function Brca1ClassifierBody({ hgvsList }: { hgvsList: string[] }) {
  return (
    <div className="flex-1 flex flex-col justify-end min-h-[5rem]">
      <div className="space-y-3">
        {hgvsList.map((hgvs) => (
          <Brca1FunctionCard key={hgvs} hgvsProtein={hgvs} />
        ))}
      </div>
    </div>
  );
}
