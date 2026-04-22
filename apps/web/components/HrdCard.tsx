"use client";

import type { HrdResult } from "@/lib/bc-types";

interface Props {
  hrd: HrdResult;
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
export function HrdCard({ hrd }: Props) {
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
          is HR-proficient — it just means this tool can&apos;t tell from what
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

      <p className="text-sm leading-relaxed font-medium">{style.oneLiner}</p>
      <p className="text-sm leading-relaxed text-muted-foreground">{hrd.summary}</p>

      <div className="rounded-lg bg-white/60 border p-3 md:p-4 text-sm leading-relaxed">
        <div className="text-xs font-medium uppercase text-muted-foreground mb-1">
          What this means for PARP inhibitors
        </div>
        {hrd.parp_inhibitor_context}
      </div>

      {hrd.evidence.length > 0 ? (
        <div>
          <div className="text-xs font-medium uppercase text-muted-foreground mb-2">
            What drove this result ({hrd.evidence.length})
          </div>
          <ul className="space-y-2">
            {hrd.evidence.map((e, i) => (
              <li key={i} className="text-sm border rounded-lg p-3 bg-white/70">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="font-semibold">{e.gene}</span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {e.variant_label}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">{e.detail}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

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
