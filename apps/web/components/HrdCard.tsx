"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FlaskConical,
  Activity,
  Info,
  Scan,
  Microscope,
  FileText,
} from "lucide-react";

import { Brca1FunctionCard } from "./Brca1FunctionCard";
import { useLabResultsWriter } from "./LabResultsContext";
import {
  api,
  type CtScanResponse,
  type HRDetectResponse,
  type HrdScarResponse,
  type VariantEvidenceResponse,
} from "@/lib/api";
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
  /**
   * Cancer type ("Stage III ovarian", "metastatic breast", etc).
   * Forwarded to the variant-evidence agent so its synthesis is framed
   * for the patient's actual disease context.
   */
  indication?: string | null;
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
  indication = null,
}: Props) {
  const [tab, setTab] = useState<"result" | "lab">("result");

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
      <div className="flex-1 min-w-0 flex flex-col gap-3">
        {indeterminateTiles.length > 0 ? (
          <TabBar
            tab={tab}
            setTab={setTab}
            labTileCount={indeterminateTiles.length}
            analysisResult={analysisResult}
            patientLabel={patientLabel}
          />
        ) : null}

        <div
          className={`flex-1 min-h-0 ${
            tab === "result" || indeterminateTiles.length === 0 ? "" : "hidden"
          }`}
        >
          <section className="rounded-2xl border border-border bg-muted/40 p-5 text-sm space-y-2 h-full overflow-y-auto">
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
        </div>

        {indeterminateTiles.length > 0 ? (
          <div
            className={`flex-1 min-h-0 overflow-y-auto pr-1 -mr-1 ${
              tab === "lab" ? "" : "hidden"
            }`}
          >
            <LabSection
              tagline="Even with a clean germline panel, imaging can pick up HR-deficiency from somatic events."
              tiles={indeterminateTiles}
            />
          </div>
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

  // Lab tiles are gated on whether the patient actually uploaded the
  // record that experiment reads from. A user who picked a variant from
  // the catalog (no VCF upload) shouldn't see a "DNA-repair classifier"
  // tile claiming to read their VCF — there is no VCF. Same logic for
  // the scar tile (needs a tumor scar report) and the CT tile (needs a
  // CT scan upload). Demo patients have these uploads in their profile,
  // so all three tiles still light up for Maya / Diana / Priya.
  const hasScarData = !!recordRefs.reportFilename || !!scarPrefill;

  const tiles: React.ReactNode[] = [];
  if (classifiableBrca1Variants.length > 0) {
    tiles.push(
      <LabTile
        key="ml"
        title="DNA-repair classifier"
        tests="Tests whether your variant breaks BRCA1's repair function."
        icon={<FlaskConical className="w-4 h-4" aria-hidden />}
        recordLabel={recordRefs.vcfFilename ?? "your selected variant"}
      >
        <Brca1ClassifierBody hgvsList={classifiableBrca1Variants} />
      </LabTile>,
    );
  }
  // The variant-evidence agent (LangGraph + Claude) lives in the Result
  // tab as its own SectionCard — see below. Treating it as a "lab tile"
  // alongside ML models was a category mismatch: the lab tiles run
  // models on the patient's data, while the agent retrieves public
  // evidence and formats it. The Result tab is the right home — it's
  // where the patient sees what we know *about* their data, separate
  // from what we predicted *from* their data.
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
  if (hrd.label !== "hr_proficient" && hasScarData) {
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
  // HRDetect always renders. The user can upload a VCF inside the tile;
  // the signature-extraction step is a documented stub but the
  // logistic-regression evaluation is real.
  tiles.push(
    <LabTile
      key="hrdetect"
      title="HRDetect (WGS signature classifier)"
      tests="Davies 2017 — six WGS signature features into a logistic regression."
      icon={<FlaskConical className="w-4 h-4" aria-hidden />}
      recordLabel="VCF upload (optional)"
    >
      <HrdetectBody />
    </LabTile>,
  );

  // Agent runs against public databases keyed only on gene + variant, so it
  // works whether the variant came from a VCF upload (preset patients) or
  // from the /build catalog picker. Show it whenever we have a variant.
  const showAgent = variantEvidence.length > 0;

  return (
    <div className="flex-1 min-w-0 flex flex-col gap-3">
      <TabBar
        tab={tab}
        setTab={setTab}
        labTileCount={tiles.length}
        analysisResult={analysisResult}
        patientLabel={patientLabel}
      />

      {/* Both tabs stay mounted — we toggle visibility via `hidden` rather
          than conditionally rendering — so the lab tiles' state (CT model
          result, scar score result, BRCA1 classifier output) survives
          tab switches instead of re-running the experiments on every flip
          back. React Query handles the BRCA1 case automatically; the CT
          and scar panels need this trick because their state is local. */}
      <div
        className={`flex-1 min-h-0 ${
          tab === "result" || tiles.length === 0 ? "" : "hidden"
        }`}
      >
        {/* One unified card — agent at the top, then HR status below.
            Card is height-bounded by the right column so the page never
            needs to scroll; the inner body scrolls if the agent prose
            overflows. */}
        <SectionCard label="Clinical evidence & HR-deficiency status" fillHeight>
          <div className="flex-1 min-h-0 overflow-y-auto pr-1 -mr-1 space-y-4">
            {showAgent ? (
              <VariantEvidenceAgentBody
                gene={variantEvidence[0].gene}
                variant={stripGenePrefix(
                  variantEvidence[0].variant_label,
                  variantEvidence[0].gene,
                )}
                indication={indication}
              />
            ) : null}

            <div
              className={`space-y-3 ${
                showAgent ? "border-t pt-4" : ""
              }`}
            >
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground font-semibold">
                HR-deficiency status
              </div>
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

              {variantEvidence.length > 0 ? (
                <div className="flex items-baseline gap-2 flex-wrap pt-1">
                  <span className="text-[11px] uppercase tracking-wide text-muted-foreground font-semibold">
                    Based on
                  </span>
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
              ) : null}
            </div>
          </div>
        </SectionCard>
      </div>

      {tiles.length > 0 ? (
        <div
          className={`flex-1 min-h-0 overflow-y-auto pr-1 -mr-1 ${
            tab === "lab" ? "" : "hidden"
          }`}
        >
          <LabSection
            tagline={`${tiles.length === 1 ? "One experiment" : `${tiles.length} independent experiments`} testing whether your tumor is HR-deficient. Each runs on a different record from your profile.`}
            tiles={tiles}
          />
        </div>
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
  fillHeight = false,
}: {
  label: string;
  children: React.ReactNode;
  /** When true, the card stretches to fill its parent and its body
   *  becomes a flex column so an inner overflow-y-auto child can scroll
   *  independently of the outer page. */
  fillHeight?: boolean;
}) {
  const shell = fillHeight
    ? "rounded-2xl border bg-card overflow-hidden h-full flex flex-col"
    : "rounded-2xl border bg-card overflow-hidden";
  const body = fillHeight
    ? "p-4 md:p-5 flex-1 min-h-0 flex flex-col gap-3"
    : "p-4 md:p-5 space-y-3";
  return (
    <div className={shell}>
      <div className="h-px bg-gradient-to-r from-amber-400/40 via-amber-500 to-amber-400/40" />
      <div className={body}>
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
      {labTileCount > 0 ? (
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
          <span className="text-[11px] rounded-full bg-amber-100 text-amber-800 px-1.5 py-0.5 font-mono">
            {labTileCount}
          </span>
        </button>
      ) : null}
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
  const writer = useLabResultsWriter();

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
        if (!cancelled) {
          setResult(resp);
          writer?.setScar(resp);
        }
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
      writer?.setScar(resp);
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
  const writer = useLabResultsWriter();

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
        if (!cancelled) {
          setResult(out);
          writer?.setCt(out);
        }
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
    // writer is stable from context, intentionally not in deps so a
    // re-render doesn't refetch the CT scan.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
          <div key={hgvs}>
            <Brca1ResultPublisher hgvsProtein={hgvs} />
            <Brca1FunctionCard hgvsProtein={hgvs} />
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Headless adapter that re-runs the same React-Query call the
 * Brca1FunctionCard uses (the cache is shared by query key) and writes
 * the result into the LabResultsContext as soon as it's available.
 * Renders nothing — purely a side-effect bridge from React Query into
 * the lab-results context the chat reads from.
 */
function Brca1ResultPublisher({ hgvsProtein }: { hgvsProtein: string }) {
  const writer = useLabResultsWriter();
  const q = useQuery({
    queryKey: ["brca1", hgvsProtein],
    queryFn: () => api.classifyBrca1(hgvsProtein),
    retry: 1,
  });
  useEffect(() => {
    if (q.data) writer?.setBrca1(hgvsProtein, q.data);
    // No cleanup-on-unmount — the chat may still want to reference the
    // last result even if the lab tab gets re-mounted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.data, hgvsProtein]);
  return null;
}

/**
 * HRDetect tile body. Lets the user upload a VCF; backend stubs
 * signature extraction (real WGS extraction needs SigProfiler) and
 * runs the published Davies 2017 logistic regression. The tile is
 * explicit about which step is real vs stubbed via the caveats list
 * the API returns.
 */
function HrdetectBody() {
  const [file, setFile] = useState<File | null>(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<HRDetectResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const writer = useLabResultsWriter();

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setErr(null);
    setRunning(true);
    try {
      const resp = await api.scoreHrdetectVcf(f);
      setResult(resp);
      writer?.setHrdetect(resp);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "HRDetect failed");
    } finally {
      setRunning(false);
    }
  }

  const labelText: Record<HRDetectResponse["label"], string> = {
    predicted_hr_deficient: "Predicted HR-deficient",
    predicted_hr_proficient: "Predicted HR-proficient",
    uncertain: "Uncertain",
  };
  const labelStyles: Record<HRDetectResponse["label"], string> = {
    predicted_hr_deficient: "text-success bg-success/10 border-success/40",
    predicted_hr_proficient: "text-muted-foreground bg-muted border-border",
    uncertain: "text-warning bg-warning/10 border-warning/40",
  };

  return (
    <div className="flex-1 flex flex-col gap-3 min-h-[5rem]">
      <label className="block">
        <span className="sr-only">Upload VCF for HRDetect</span>
        <input
          type="file"
          accept=".vcf,.vcf.gz"
          onChange={onFile}
          disabled={running}
          className="block w-full text-xs file:mr-3 file:rounded-md file:border-0 file:bg-amber-100 file:text-amber-800 file:px-3 file:py-1.5 file:text-xs file:font-medium hover:file:bg-amber-200 disabled:opacity-60"
        />
      </label>
      {file ? (
        <p className="text-[11px] text-muted-foreground italic truncate">
          {running ? "Scoring " : "Scored "}
          {file.name}
        </p>
      ) : null}
      {err ? <p className="text-xs text-red-600">{err}</p> : null}
      {result ? (
        <div className="space-y-2">
          <div
            className={`rounded-lg border p-3 text-sm ${labelStyles[result.label]}`}
          >
            <div className="flex items-baseline justify-between gap-2 flex-wrap">
              <span className="font-semibold">{labelText[result.label]}</span>
              <span className="text-xs">
                {Math.round(result.probability * 100)}% p(HRD)
              </span>
            </div>
            <details className="mt-2 text-xs">
              <summary className="cursor-pointer opacity-80 hover:opacity-100">
                Caveats &amp; signature features
              </summary>
              <ul className="mt-1 space-y-1 list-disc pl-5 opacity-90">
                {result.caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
              <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 opacity-90">
                <li>HRD-LOH: {result.features.hrd_loh.toFixed(1)}</li>
                <li>e.del.mh: {result.features.e_del_mh_prop.toFixed(2)}</li>
                <li>SBS3: {result.features.sbs3.toFixed(2)}</li>
                <li>SBS8: {result.features.sbs8.toFixed(2)}</li>
                <li>RS3: {result.features.rs3.toFixed(2)}</li>
                <li>RS5: {result.features.rs5.toFixed(2)}</li>
              </ul>
            </details>
          </div>
        </div>
      ) : (
        <p className="text-[11px] text-muted-foreground leading-snug">
          Upload a VCF to run HRDetect. The signature-extraction step is
          a documented demo stub (real WGS extraction needs SigProfiler);
          the logistic regression that produces the score is real.
        </p>
      )}
    </div>
  );
}

/**
 * Variant-evidence agent body, rendered inside a Result-tab SectionCard.
 *
 * Calls the LangGraph endpoint that fans out to ClinVar / OpenFDA /
 * gnomAD in parallel and asks Claude to synthesize the retrieved
 * evidence into a clinician-readable paragraph (with the synthesis
 * prompt constrained — Claude formats, doesn't invent).
 *
 * Layout choices for readability:
 *   - Summary paragraph rendered at the section's body size with
 *     comfortable line-height; this is the main thing the patient reads.
 *   - Source-status pills below the paragraph show at a glance which
 *     databases returned data, which were unavailable, and which errored.
 *   - The constrained-by-prompt disclosure is a single small line, not
 *     a header-level statement.
 *   - Raw evidence stays auditable but tucked into a Details expander.
 */
function VariantEvidenceAgentBody({
  gene,
  variant,
  indication = null,
}: {
  gene: string;
  variant: string;
  indication?: string | null;
}) {
  const query = useQuery<VariantEvidenceResponse>({
    queryKey: ["variant-evidence", gene, variant, indication],
    queryFn: () => api.variantEvidence(gene, variant, indication),
    retry: 0,
    staleTime: 5 * 60_000,
  });

  if (query.isLoading) {
    return (
      <p className="text-xs text-muted-foreground italic">
        Querying ClinVar, OpenFDA, gnomAD…
      </p>
    );
  }
  if (query.isError) {
    return (
      <p className="text-xs text-red-600">
        Agent failed: {(query.error as Error).message}
      </p>
    );
  }
  if (!query.data) return null;

  const r = query.data;
  const sourceMeta: { key: string; label: string; status: string }[] = [
    { key: "clinvar", label: "ClinVar",  status: getStatus(r.evidence.clinvar) },
    { key: "openfda", label: "OpenFDA",  status: getStatus(r.evidence.openfda) },
    { key: "gnomad",  label: "gnomAD",   status: getStatus(r.evidence.gnomad)  },
  ];

  return (
    <div className="space-y-3">
      {/* Headline: the one sentence the patient should walk away with. */}
      {r.pathogenicity ? (
        <p className="text-base font-medium leading-snug text-foreground">
          {r.pathogenicity}
        </p>
      ) : null}

      {/* Rarity sits as a quiet caption right under the headline so it
          reads as one thought ("...harmful. Very rare in gnomAD.") */}
      {r.rarity ? (
        <p className="text-xs text-muted-foreground leading-snug">
          {r.rarity}
        </p>
      ) : null}

      {/* Drug list — visually distinct from the prose. Compact rows,
          one drug per line: bold generic, lighter brand, very short
          indication. */}
      {r.drugs.length > 0 ? (
        <div className="space-y-1.5">
          <h5 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            FDA-approved
          </h5>
          <ul className="divide-y rounded-lg border bg-white">
            {r.drugs.map((d) => (
              <li key={d.generic} className="px-3 py-2 text-sm">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="font-semibold capitalize">{d.generic}</span>
                  {d.brand ? (
                    <span className="text-[11px] text-muted-foreground">
                      {d.brand}
                    </span>
                  ) : null}
                  {d.indication ? (
                    <span className="text-[11px] text-muted-foreground">
                      · {d.indication}
                    </span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Sources + provenance collapsed into one quiet row. */}
      <div className="flex items-center justify-between gap-2 flex-wrap pt-1">
        <div className="flex flex-wrap gap-1">
          {sourceMeta.map((s) => (
            <SourcePill key={s.key} label={s.label} status={s.status} />
          ))}
        </div>
        <span className="text-[10px] text-muted-foreground italic">
          {r.model.startsWith("claude") ? "Claude" : r.model} · {(r.duration_ms / 1000).toFixed(1)}s
        </span>
      </div>
    </div>
  );
}

/**
 * Translate a tool's response status into a 3-bucket UI state. Anything
 * other than "ok" is shown as either "missing" (intentional gaps like
 * gnomAD's "absent") or "error" (transient failure). Three buckets keep
 * the source pills scannable.
 */
function getStatus(payload: Record<string, unknown> | null): string {
  if (!payload) return "error";
  const s = String(payload.status ?? "");
  if (s === "ok") return "ok";
  if (s === "error") return "error";
  return "missing"; // not_found, absent, auth_required, no_curated_drugs
}

function SourcePill({ label, status }: { label: string; status: string }) {
  const styles =
    status === "ok"
      ? "bg-success/10 text-success border-success/30"
      : status === "missing"
        ? "bg-muted text-muted-foreground border-border"
        : "bg-warning/10 text-warning border-warning/30";
  const symbol = status === "ok" ? "✓" : status === "missing" ? "—" : "⚠";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${styles}`}
    >
      <span aria-hidden>{symbol}</span>
      {label}
    </span>
  );
}
