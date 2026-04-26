"use client";

import { useState } from "react";
import { FlaskConical, Activity, Clock, Info, Scan } from "lucide-react";

import { Brca1FunctionCard } from "./Brca1FunctionCard";
import { api, type CtScanResponse, type HrdScarResponse } from "@/lib/api";
import type { HrdResult } from "@/lib/bc-types";

// Drugs in the PARP-inhibitor class. When the patient's current drug is one
// of these AND they have HR-deficient evidence, we surface a reversion-
// monitoring callout — a scar-based HRD score is historical (it records the
// tumor's past HR state), and ~20-30% of PARPi-treated BRCA-associated
// tumors develop reversion mutations that restore HR repair under drug
// pressure (Silverman & Schonhoft, Clin Cancer Res 2025). The Myriad scar
// cutoff of 42 doesn't see that reversion.
const PARP_INHIBITOR_DRUG_IDS = new Set(["olaparib", "niraparib", "rucaparib", "talazoparib"]);

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
}

/**
 * HR-deficiency composite card. Tells the patient (and their oncologist)
 * whether their variants make the tumor PARP-inhibitor-eligible under
 * current FDA biomarker logic.
 *
 * When HRD is indeterminate AND there's no HR-relevant evidence, we render
 * a compact "not applicable" note instead of the full card. The big amber
 * "Indeterminate" block was confusing patients whose actual finding was
 * elsewhere (e.g. Diana has a CYP2D6 metabolism variant, not an HR variant
 * — her HRD status genuinely isn't the story).
 */
export function HrdCard({
  hrd,
  classifiableBrca1Variants = [],
  drugId = null,
  ctScanUrl = null,
  ctScanLabel = null,
}: Props) {
  const showReversionCallout =
    hrd.label === "hr_deficient" &&
    !!drugId &&
    PARP_INHIBITOR_DRUG_IDS.has(drugId);
  // Compact "not applicable" rendering for patients without HR-panel variants.
  // When a CT fixture is provided we still render the radiogenomics panel so
  // the patient sees that even a germline-clean result doesn't rule out an
  // HR-deficient tumor (somatic BRCA loss, BRCA1 promoter methylation, etc.).
  if (hrd.label === "indeterminate" && hrd.evidence.length === 0) {
    return (
      <section className="rounded-2xl border border-border bg-muted/40 p-4 md:p-5 text-sm space-y-4">
        <div className="space-y-2">
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                HR-deficiency status
              </div>
              <div className="font-medium">Not assessed</div>
            </div>
            <span className="text-[11px] text-muted-foreground">Score 0 / 100</span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Your variants aren&apos;t in the HR-repair panel (BRCA1, BRCA2, PALB2,
            ATM, RAD51C/D, BRIP1, BARD1, FANC). That doesn&apos;t mean your tumor
            is HR-proficient. It just means this tool can&apos;t tell from what
            you&apos;ve entered. A clinical hereditary-cancer panel (Myriad, Ambry,
            Invitae) covers thousands more variants.
          </p>
        </div>

        {ctScanUrl ? (
          <div className="rounded-lg border-l-4 border-primary/60 bg-primary/5 p-3 md:p-4 space-y-2">
            <div className="flex items-center gap-2 text-xs uppercase tracking-wide font-semibold text-primary">
              <Info className="w-3.5 h-3.5" aria-hidden />
              A clean germline panel doesn&apos;t rule out HRD
            </div>
            <p className="text-sm leading-relaxed">
              Roughly one in three HR-deficient ovarian tumors have no inherited
              BRCA-family mutation. The deficiency comes from somatic events
              the germline panel can&apos;t see: BRCA1 promoter methylation, a
              somatic BRCA1/2 hit acquired by the tumor, or loss of another HR
              gene. Imaging-based HRD prediction is a non-invasive pre-screen
              that can flag these patients so their oncologist knows to order
              tumor sequencing.
            </p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Run the radiogenomics model below on {ctScanLabel ?? "this CT scan"}
              {" "}to see what it predicts.
            </p>
          </div>
        ) : null}

        {ctScanUrl ? (
          <RadiogenomicsCtPanel
            ctScanUrl={ctScanUrl}
            ctScanLabel={ctScanLabel ?? "this CT scan"}
            currentDrugId={drugId}
          />
        ) : null}
      </section>
    );
  }

  const style = {
    hr_deficient: {
      bg: "bg-success/10",
      border: "border-success/40",
      pill: "bg-success/20 text-success",
      label: "HR-deficient",
      oneLiner: "Your variants suggest the tumor can't repair DNA double-strand breaks well. PARP inhibitors may be an option.",
    },
    hr_proficient: {
      bg: "bg-muted",
      border: "border-border",
      pill: "bg-muted text-foreground",
      label: "HR-proficient",
      oneLiner: "Your HR-repair genes look intact. PARP inhibitors are unlikely to be prioritized unless tumor testing says otherwise.",
    },
    indeterminate: {
      bg: "bg-warning/10",
      border: "border-warning/40",
      pill: "bg-warning/20 text-warning",
      label: "Mixed signals",
      oneLiner: "Some HR-panel variants are present, but not enough to make a confident call. Worth discussing with your oncologist.",
    },
  }[hrd.label];

  return (
    <section
      className={`rounded-2xl border p-5 md:p-6 space-y-4 ${style.bg} ${style.border}`}
    >
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <div>
            <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
              HR-deficiency result
            </div>
            <h3 className="text-lg md:text-xl font-semibold">{style.label}</h3>
          </div>
          {showReversionCallout ? <ReversionAwarenessInfo /> : null}
        </div>
        <div className={`px-3 py-1.5 rounded-full text-sm font-semibold ${style.pill}`}>
          Score {hrd.score} / 100
        </div>
      </header>

      <p className="text-sm leading-relaxed">{style.oneLiner}</p>

      {(() => {
        // When the inline BRCA1 classifier card is being offered, drop the
        // `ml_prediction` rows from the evidence list — the nested card is
        // the canonical UI for the ML output. Otherwise the same variant
        // shows up twice ("What drove this result" row + the model card).
        const hideMl = classifiableBrca1Variants.length > 0;
        const filtered = hideMl
          ? hrd.evidence.filter((e) => e.source !== "ml_prediction")
          : hrd.evidence;
        if (filtered.length === 0) return null;
        return (
          <div>
            <div className="text-xs font-medium uppercase text-muted-foreground mb-2">
              What drove this result ({filtered.length})
            </div>
            <ul className="space-y-2">
              {filtered.map((e, i) => (
                <li key={i} className="text-sm border rounded-lg p-3 bg-white/70">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="font-semibold">{e.gene}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {stripGenePrefix(e.variant_label, e.gene)}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">{e.detail}</p>
                </li>
              ))}
            </ul>
          </div>
        );
      })()}

      {classifiableBrca1Variants.length > 0 ? (
        <Brca1PredictionNested hgvsList={classifiableBrca1Variants} />
      ) : null}

      {ctScanUrl ? (
        <RadiogenomicsCtPanel
          ctScanUrl={ctScanUrl}
          ctScanLabel={ctScanLabel ?? "this CT scan"}
        />
      ) : null}

      <TumorScarPanel />

      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer hover:text-foreground">
          Caveats
        </summary>
        <ul className="mt-2 space-y-1 list-disc pl-5">
          {hrd.caveats.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}

/**
 * Compact form for users who have a Myriad myChoice / FoundationOne CDx
 * report and want to run the three feature counts through our scar
 * scorer. This complements the germline-variant HRD call above: the
 * germline score tells you whether the patient is an HR-repair carrier,
 * this tumor-scar score tells you whether the tumor is *currently*
 * HR-deficient — the FDA biomarker question for PARP-inhibitor eligibility.
 */
function TumorScarPanel() {
  const [open, setOpen] = useState(false);
  const [loh, setLoh] = useState("");
  const [lst, setLst] = useState("");
  const [ntai, setNtai] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<HrdScarResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

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

  if (!open) {
    return (
      <div className="rounded-lg border-2 border-dashed border-muted-foreground/30 p-3 flex items-center gap-3 flex-wrap">
        <Activity className="w-4 h-4 text-primary flex-shrink-0" aria-hidden />
        <div className="flex-1 min-w-[180px] text-sm">
          <div className="font-medium">
            Already have a myChoice or FoundationOne CDx report?
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            If your doctor ran one of those tumor tests, type in the three
            scar numbers they printed and we&apos;ll translate them into
            plain English.
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex items-center justify-center rounded-lg bg-primary text-primary-foreground px-3 py-1.5 text-xs font-medium hover:opacity-90 transition-opacity"
        >
          Enter numbers
        </button>
      </div>
    );
  }

  const labelStyles: Record<HrdScarResponse["label"], string> = {
    hr_deficient_scar: "text-success bg-success/10 border-success/40",
    borderline_scar: "text-warning bg-warning/10 border-warning/40",
    hr_proficient_scar: "text-muted-foreground bg-muted border-border",
    insufficient: "text-muted-foreground bg-muted border-border",
  };
  const labelText: Record<HrdScarResponse["label"], string> = {
    hr_deficient_scar: "HR-deficient (tumor scar signal)",
    borderline_scar: "Borderline scar burden",
    hr_proficient_scar: "HR-proficient (low scar burden)",
    insufficient: "Insufficient data",
  };

  return (
    <div className="rounded-lg border bg-white/60 p-3 md:p-4 space-y-3">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground font-semibold">
        <Activity className="w-3.5 h-3.5 text-primary" aria-hidden />
        Tumor HRD scar score
      </div>

      <form onSubmit={onSubmit} className="flex flex-wrap gap-2 items-end">
        <LabeledNumber label="HRD-LOH" value={loh} onChange={setLoh} />
        <LabeledNumber label="LST" value={lst} onChange={setLst} />
        <LabeledNumber label="NTAI" value={ntai} onChange={setNtai} />
        <button
          type="submit"
          disabled={running || !loh || !lst || !ntai}
          className="inline-flex items-center justify-center rounded-lg bg-primary text-primary-foreground px-3 py-1.5 text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {running ? "Scoring…" : "Score"}
        </button>
      </form>
      {err ? <p className="text-xs text-red-600">{err}</p> : null}

      {result ? (
        <div className={`rounded-lg border p-3 space-y-2 text-sm ${labelStyles[result.label]}`}>
          <div className="flex items-baseline justify-between gap-2 flex-wrap">
            <span className="font-semibold">{labelText[result.label]}</span>
            <span className="text-xs">HRD-sum {result.hrd_sum} / 100</span>
          </div>
          <p className="text-xs leading-relaxed">{result.summary}</p>
          <p className="text-xs leading-relaxed">{result.interpretation}</p>
        </div>
      ) : null}

      <p className="text-[11px] text-muted-foreground leading-relaxed">
        Scar scoring needs paired tumor/normal sequencing from a genome-graph
        SV pipeline (<code>vg call</code> or <code>minigraph</code>) or a
        clinical assay produces these three counts. See the README for the
        end-to-end Snakemake pipeline.
      </p>
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
        className="w-20 border rounded px-2 py-1 bg-white text-sm"
        placeholder="0"
      />
    </label>
  );
}

/**
 * Collapsible info button that surfaces the reversion-awareness caveat for
 * PARPi patients. Click the ⓘ icon next to the HR-deficient pill and a
 * popover shows why a scar-based HRD call is *historical* — ~20-30% of
 * PARPi-responding BRCA tumors develop reversion mutations under drug
 * pressure that restore HR repair, which scar scores can't see.
 *
 * Based on Silverman & Schonhoft, Clin Cancer Res 2025 (Repare TRESR/ATTACC
 * trials, 44% reversions in BRCA-associated post-PARPi tumors) and the
 * PRIMA / PAOLA-1 observation that ~30% of Myriad-HRD-positive patients fail
 * PARPi. The right follow-up is serial ctDNA monitoring for in-frame
 * restoring indels near the pathogenic locus.
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
            your oncologist about <strong>serial ctDNA testing</strong> to catch
            reversion mutations early.
          </p>
          <p className="text-xs text-muted-foreground pt-2 border-t border-warning/20">
            Source: Silverman &amp; Schonhoft, Clinical Cancer Research, 2025
            (Repare TRESR / ATTACC trials).
          </p>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Nested "run the radiogenomics CT model" panel.
 *
 * For demo patients who ship with a fixture CT (currently just Maya's
 * synthetic ovarian-pelvis scan), this panel pulls the NIfTI, uploads it
 * to /api/radiogenomics/upload, and renders the model's HR-deficiency
 * probability + caveats inline. The scan itself is shown in the left-column
 * 3D slideshow; this panel is the "run the model" action, paired with
 * the other HR-deficiency evidence.
 */
function RadiogenomicsCtPanel({
  ctScanUrl,
  ctScanLabel,
  currentDrugId = null,
}: {
  ctScanUrl: string;
  ctScanLabel: string;
  currentDrugId?: string | null;
}) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<CtScanResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function onRun() {
    setErr(null);
    setRunning(true);
    try {
      const resp = await fetch(ctScanUrl);
      if (!resp.ok) throw new Error(`could not fetch ${ctScanUrl}`);
      const blob = await resp.blob();
      const name = ctScanUrl.split("/").pop() ?? "ct_scan.nii.gz";
      const file = new File([blob], name, { type: "application/gzip" });
      const out = await api.uploadCtScan(file);
      setResult(out);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "CT upload failed");
    } finally {
      setRunning(false);
    }
  }

  // One-click panel. The teaser + "Show run panel" intermediate step used to
  // collapse the action behind two clicks; now the card always shows a
  // single "Run radiogenomics model" button and the result renders inline
  // below it on success.
  return (
    <div className="rounded-lg border bg-white/60 p-3 md:p-4 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-2 min-w-[180px] flex-1">
          <Scan className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" aria-hidden />
          <div className="text-sm">
            <div className="font-medium">
              Predict HRD from {ctScanLabel}{" "}
              <span className="text-xs font-normal text-muted-foreground">
                · experimental radiogenomics ML
              </span>
            </div>
            <div className="text-xs text-muted-foreground">
              Runs a 3D CNN trained on TCGA-OV paired imaging + genomics to
              estimate HR-deficiency from the preoperative CT alone.
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={onRun}
          disabled={running}
          className="inline-flex items-center justify-center rounded-lg bg-primary text-primary-foreground px-3 py-1.5 text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-opacity flex-shrink-0"
        >
          {running ? "Running…" : result ? "Re-run" : "Run radiogenomics model"}
        </button>
      </div>

      {err ? <p className="text-xs text-red-600">{err}</p> : null}
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

  // Action callout: surface a tumor-sequencing + PARP-inhibitor conversation
  // ONLY when (a) the model called HR-deficient and (b) the patient isn't
  // already on a PARP inhibitor. For Maya (already on olaparib) the prompt
  // would be redundant; for Diana (on tamoxifen with a CYP2D6 PGx issue
  // that already reduces tamoxifen activity) it's the actually-useful next
  // clinical step.
  const showParpCallout =
    result.label === "predicted_hr_deficient" &&
    !!currentDrugId &&
    !PARP_INHIBITOR_DRUG_IDS.has(currentDrugId);

  return (
    <div className="space-y-3">
      <div className={`rounded-lg border p-3 space-y-2 text-sm ${labelStyles[result.label]}`}>
        <div className="flex items-baseline justify-between gap-2 flex-wrap">
          <span className="font-semibold">{labelText[result.label]}</span>
          <span className="text-xs">
            p(HRD) = {result.hrd_probability.toFixed(2)} · {result.confidence} confidence
          </span>
        </div>
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
            Model caveats ({result.caveats.length})
          </summary>
          <ul className="mt-2 space-y-1 list-disc pl-5 text-muted-foreground">
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

/**
 * Action callout that ties an HR-deficient imaging prediction to the next
 * clinical step. The radiogenomics model isn't a diagnostic on its own —
 * it's a pre-screen — so the recommendation chain is:
 *
 *   imaging-flagged HRD  ->  tumor sequencing to confirm  ->  if confirmed,
 *   discuss PARP-inhibitor eligibility (olaparib / niraparib / rucaparib)
 *   instead of (or in addition to) the current non-PARP regimen.
 *
 * For tamoxifen-on-poor-CYP2D6 specifically (Diana's scenario) the
 * conversation is doubly motivated: the current drug isn't being activated
 * efficiently AND a new line of HRD-targeted therapy is potentially open.
 * We surface the tamoxifen-specific framing when we can detect it.
 */
function ParpInhibitorActionCallout({ currentDrugId }: { currentDrugId: string }) {
  const isTamoxifen = currentDrugId === "tamoxifen";
  return (
    <div className="rounded-lg border-l-4 border-primary/60 bg-primary/5 p-3 md:p-4 space-y-2 text-sm">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide font-semibold text-primary">
        <Info className="w-3.5 h-3.5" aria-hidden />
        Worth asking your oncologist about
      </div>
      {isTamoxifen ? (
        <p className="leading-relaxed">
          Two findings line up here. Your CYP2D6 *4/*4 status is reducing how
          much active tamoxifen your body produces, AND the imaging-based HRD
          predictor flagged your tumor as HR-deficient. Together that&apos;s a
          strong case to discuss the next steps below at your next appointment.
        </p>
      ) : (
        <p className="leading-relaxed">
          The imaging-based HRD predictor flagged your tumor as HR-deficient
          even though your germline variants don&apos;t explain it. That&apos;s
          worth bringing up at your next appointment. Two next steps to discuss:
        </p>
      )}
      <ol className="list-decimal pl-5 space-y-1 leading-relaxed">
        <li>
          <strong>Confirm with tumor sequencing.</strong> A Myriad myChoice or
          FoundationOne CDx test scores HRD directly from the tumor and
          catches somatic mechanisms (BRCA1 promoter methylation, somatic
          BRCA loss) that a germline panel can&apos;t see.
        </li>
        <li>
          <strong>If HRD is confirmed, ask about PARP inhibitors.</strong>{" "}
          Olaparib (Lynparza), niraparib (Zejula), and rucaparib (Rubraca)
          are FDA-approved for HRD-positive ovarian cancer and may be a
          better fit than {isTamoxifen ? "tamoxifen alone" : "your current treatment alone"}.
        </li>
      </ol>
      <p className="text-xs text-muted-foreground pt-1">
        This is research-only software. Confirm any treatment change with
        your oncologist; PARP-inhibitor eligibility requires a CLIA-certified
        HRD test.
      </p>
    </div>
  );
}

/**
 * Drop a leading "{gene} " prefix from a variant label when the gene is
 * already rendered next to it in the same row, so we don't print
 * "BRCA1 BRCA1 p.Cys61Gly".
 */
function stripGenePrefix(label: string, gene: string): string {
  const prefix = `${gene} `;
  return label.startsWith(prefix) ? label.slice(prefix.length) : label;
}

/**
 * Nested BRCA1 variant-effect prediction subsection.
 *
 * The prediction takes a couple seconds and some patients won't care for the
 * ML layer at all, so it's opt-in: a compact button by default, the full
 * Brca1FunctionCard content once clicked. Lives inside HrdCard so patients
 * see it as "extra evidence for the HR-deficiency call," not as an
 * unrelated separate card further down the page.
 */
function Brca1PredictionNested({ hgvsList }: { hgvsList: string[] }) {
  const [open, setOpen] = useState(false);
  const label =
    hgvsList.length > 1 ? "these BRCA1 variants" : "this BRCA1 variant";

  if (!open) {
    return (
      <div className="rounded-lg border-2 border-dashed border-muted-foreground/30 p-3 flex items-center gap-3 flex-wrap">
        <FlaskConical className="w-4 h-4 text-primary flex-shrink-0" aria-hidden />
        <div className="flex-1 min-w-[180px] text-sm">
          <div className="font-medium">
            Predict {label}{" "}
            <span className="text-xs font-normal text-muted-foreground">
              · experimental ML
            </span>
          </div>
          <div className="text-xs text-muted-foreground font-mono truncate">
            {hgvsList.join(", ")}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex items-center justify-center rounded-lg bg-primary text-primary-foreground px-3 py-1.5 text-xs font-medium hover:opacity-90 transition-opacity"
        >
          Run prediction
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-white/60 p-3 md:p-4 space-y-3">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground font-semibold">
        <FlaskConical className="w-3.5 h-3.5 text-primary" aria-hidden />
        ML prediction · experimental
      </div>
      {hgvsList.map((hgvs) => (
        <Brca1FunctionCard key={hgvs} hgvsProtein={hgvs} />
      ))}
    </div>
  );
}
