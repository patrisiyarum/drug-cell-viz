"use client";

import { useState } from "react";
import { FlaskConical, Activity, Clock } from "lucide-react";

import { Brca1FunctionCard } from "./Brca1FunctionCard";
import { api, type HrdScarResponse } from "@/lib/api";
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
export function HrdCard({ hrd, classifiableBrca1Variants = [], drugId = null }: Props) {
  const showReversionCallout =
    hrd.label === "hr_deficient" &&
    !!drugId &&
    PARP_INHIBITOR_DRUG_IDS.has(drugId);
  // Compact "not applicable" rendering for patients without HR-panel variants.
  if (hrd.label === "indeterminate" && hrd.evidence.length === 0) {
    return (
      <section className="rounded-2xl border border-border bg-muted/40 p-4 md:p-5 text-sm space-y-2">
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
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
            HR-deficiency result
          </div>
          <h3 className="text-lg md:text-xl font-semibold">
            {style.label}
          </h3>
        </div>
        <div className={`px-3 py-1.5 rounded-full text-sm font-semibold ${style.pill}`}>
          Score {hrd.score} / 100
        </div>
      </header>

      <p className="text-sm leading-relaxed">{style.oneLiner}</p>

      <div className="rounded-lg bg-white/60 border p-3 text-sm leading-relaxed">
        <div className="text-[11px] font-medium uppercase text-muted-foreground mb-1">
          PARP inhibitors
        </div>
        {hrd.parp_inhibitor_context}
      </div>

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

      {showReversionCallout ? <ReversionAwarenessNote /> : null}

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
 * A short patient-facing note that reminds someone on a PARP inhibitor that
 * the HR-deficient call is *historical* — it reflects the tumor's past HR
 * state, not its current state. Roughly 20-30% of PARPi-responding BRCA-
 * associated tumors develop reversion mutations under drug pressure that
 * quietly restore HR repair; scar-based scores (including ours) don't see
 * that because the scars are permanent records.
 *
 * Based on Silverman & Schonhoft, Clin Cancer Res 2025 (Repare TRESR/ATTACC
 * trials, 44% reversions in BRCA-associated post-PARPi tumors) and the
 * PRIMA / PAOLA-1 observation that ~30% of Myriad-HRD-positive patients fail
 * PARPi. The right follow-up is serial ctDNA monitoring for in-frame-
 * restoring indels near the pathogenic locus.
 */
function ReversionAwarenessNote() {
  return (
    <div className="rounded-lg border-l-4 border-warning bg-warning/10 p-3 md:p-4 text-sm space-y-2">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide font-semibold text-warning">
        <Clock className="w-3.5 h-3.5" aria-hidden />
        Reversion awareness
      </div>
      <p className="leading-relaxed">
        An HR-deficient result is <strong>historical</strong>. It describes
        the tumor&apos;s past DNA-repair state, not its current one.
      </p>
      <p className="leading-relaxed text-muted-foreground">
        Roughly 20 to 30 percent of BRCA-associated tumors treated with a
        PARP inhibitor develop small &ldquo;reversion&rdquo; mutations that
        quietly restore the broken BRCA gene under drug pressure. When that
        happens the tumor is no longer HR-deficient, but the scar-based
        score on this card won&apos;t reflect it (the scars are permanent).
      </p>
      <p className="leading-relaxed text-muted-foreground">
        If you&apos;ve been on a PARP inhibitor for six months or more, ask
        your oncologist about <strong>serial ctDNA testing</strong> to catch
        reversion mutations early.
      </p>
      <p className="text-xs text-muted-foreground pt-1 border-t border-warning/20">
        Source: Silverman &amp; Schonhoft, Clinical Cancer Research, 2025
        (Repare TRESR / ATTACC trials).
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
