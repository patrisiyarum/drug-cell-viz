"use client";

import type { CurrentDrugAssessment } from "@/lib/bc-types";

interface Props {
  assessment: CurrentDrugAssessment;
  onSwitchDrug?: (drugId: string) => void;
}

/**
 * "Is my current drug right for me?" card — the second-opinion feature.
 *
 * For a patient who already knows their variants AND which drug they've been
 * prescribed, this card gives a one-sentence verdict (well matched / review
 * needed / etc) rather than making them parse CPIC rule text. Any strictly
 * better-matched drugs show as quick-switch chips.
 *
 * The card's headline already names the drug — we deliberately don't render
 * a separate "Is {drugName} the right drug for you?" label above it, because
 * that ended up restating the headline nearly verbatim.
 */
export function CurrentDrugAssessmentCard({
  assessment,
  onSwitchDrug,
}: Props) {
  const style = {
    well_matched: {
      bg: "bg-success/10",
      border: "border-success/40",
      pill: "bg-success/20 text-success",
      label: "Well matched",
    },
    acceptable: {
      bg: "bg-muted",
      border: "border-border",
      pill: "bg-muted text-foreground",
      label: "Acceptable",
    },
    review_needed: {
      bg: "bg-warning/10",
      border: "border-warning/40",
      pill: "bg-warning/20 text-warning",
      label: "Review needed",
    },
    unknown: {
      bg: "bg-muted",
      border: "border-border",
      pill: "bg-muted text-foreground",
      label: "Not enough data",
    },
  }[assessment.verdict];

  return (
    <section
      className={`rounded-2xl border p-5 md:p-6 space-y-4 ${style.bg} ${style.border}`}
    >
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <h3 className="text-lg md:text-xl font-semibold flex-1 min-w-0">
          {assessment.headline}
        </h3>
        <div
          className={`px-3 py-1.5 rounded-full text-sm font-semibold flex-shrink-0 ${style.pill}`}
        >
          {style.label}
        </div>
      </header>

      <div className="space-y-2">
        {splitSentences(assessment.rationale).map((sentence, i) => (
          <p key={i} className="text-sm leading-relaxed">
            {sentence}
          </p>
        ))}
        {assessment.source ? (
          <p className="text-xs italic text-muted-foreground pt-1">
            Source: {assessment.source}
          </p>
        ) : null}
      </div>

      {assessment.better_options.length > 0 ? (
        <div className="rounded-lg border bg-white/70 p-3 md:p-4 space-y-2">
          <div className="text-xs font-medium uppercase text-muted-foreground">
            Drugs worth asking your oncologist about
          </div>
          <div className="flex flex-wrap gap-2">
            {assessment.better_options.map((opt) => (
              <button
                key={opt.id}
                onClick={() => onSwitchDrug?.(opt.id)}
                disabled={!onSwitchDrug}
                className="text-sm rounded-full border border-primary/30 bg-primary/5 px-3 py-1.5 hover:bg-primary/10 disabled:opacity-60 disabled:cursor-default transition-colors text-left"
                title={opt.reason}
                type="button"
              >
                <span className="font-medium">{opt.name}</span>
                <span className="text-muted-foreground"> — {opt.reason}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

/**
 * Break a rationale string into sentence-per-paragraph so a dense CPIC/FDA
 * recommendation text like
 *   "...breast AND ovarian cancer for germline BRCA1 pathogenic carriers.
 *   Breast: HER2-negative high-risk early or metastatic disease (OlympiA,
 *   OlympiAD). Ovarian: first-line maintenance after platinum response
 *   (SOLO-1)."
 * renders as visually separate clauses instead of a wall of text.
 *
 * Splits only on ". " followed by a capital letter / digit — leaves
 * abbreviations like "e.g." and decimals like "1.5" alone. Trailing
 * period preserved on each clause.
 */
function splitSentences(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  // Lookbehind for `.` + space + capital-letter-or-digit start of next clause.
  const parts = trimmed.split(/(?<=[.!?])\s+(?=[A-Z0-9])/);
  return parts.map((p) => p.trim()).filter(Boolean);
}
