"use client";

import type { HrdResult } from "@/lib/bc-types";

interface Props {
  hrd: HrdResult;
}

/**
 * HR-deficiency composite card. The headline output of the app — tells the
 * patient (and their oncologist) whether their variants make the tumor
 * PARP-inhibitor-eligible under current FDA biomarker logic.
 */
export function HrdCard({ hrd }: Props) {
  const style = {
    hr_deficient: {
      bg: "bg-success/10",
      border: "border-success/40",
      pill: "bg-success/20 text-success",
      label: "HR-deficient",
    },
    hr_proficient: {
      bg: "bg-muted",
      border: "border-border",
      pill: "bg-muted text-foreground",
      label: "HR-proficient",
    },
    indeterminate: {
      bg: "bg-warning/10",
      border: "border-warning/40",
      pill: "bg-warning/20 text-warning",
      label: "Indeterminate",
    },
  }[hrd.label];

  return (
    <section
      className={`rounded-2xl border p-5 md:p-6 space-y-4 ${style.bg} ${style.border}`}
    >
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
            Homologous-recombination deficiency (HRD)
          </div>
          <h3 className="text-lg md:text-xl font-semibold">
            {style.label}
          </h3>
        </div>
        <div className={`px-3 py-1.5 rounded-full text-sm font-semibold ${style.pill}`}>
          Score {hrd.score} / 100
        </div>
      </header>

      <p className="text-sm leading-relaxed">{hrd.summary}</p>

      <div className="rounded-lg bg-white/60 border p-3 md:p-4 text-sm leading-relaxed">
        <div className="text-xs font-medium uppercase text-muted-foreground mb-1">
          PARP-inhibitor context
        </div>
        {hrd.parp_inhibitor_context}
      </div>

      {hrd.evidence.length > 0 ? (
        <div>
          <div className="text-xs font-medium uppercase text-muted-foreground mb-2">
            Evidence ({hrd.evidence.length})
          </div>
          <ul className="space-y-2">
            {hrd.evidence.map((e, i) => (
              <li key={i} className="text-sm border rounded-lg p-3 bg-white/70">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="font-semibold">{e.gene}</span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {e.variant_label}
                  </span>
                  <span className="ml-auto text-[10px] uppercase text-muted-foreground">
                    weight {e.weight}
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
          Important caveats
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
