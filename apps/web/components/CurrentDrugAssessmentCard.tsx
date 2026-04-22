"use client";

import { useState } from "react";

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

      <RationaleBody rationale={assessment.rationale} source={assessment.source} />

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
 * Show only the first one or two sentences of the rationale by default and
 * tuck the long CPIC/FDA background behind a "Show clinical details" expand.
 * The first sentence is the one patient-readable takeaway ("Your BRCA1
 * p.Cys61Gly matches an FDA-approved biomarker…"); everything after is
 * trial-name + mechanism detail a patient rarely needs at first glance.
 */
function RationaleBody({
  rationale,
  source,
}: {
  rationale: string;
  source: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const sentences = splitSentences(rationale);
  if (sentences.length === 0) return null;

  const head = sentences.slice(0, 1);
  const rest = sentences.slice(1);
  const hasMore = rest.length > 0 || !!source;

  return (
    <div className="space-y-2">
      {head.map((s, i) => (
        <p key={`head-${i}`} className="text-sm leading-relaxed">
          {s}
        </p>
      ))}
      {expanded
        ? rest.map((s, i) => (
            <p key={`rest-${i}`} className="text-sm leading-relaxed">
              {s}
            </p>
          ))
        : null}
      {expanded && source ? (
        <p className="text-xs italic text-muted-foreground pt-1">
          Source: {source}
        </p>
      ) : null}
      {hasMore ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-xs text-primary hover:opacity-80 underline-offset-2 hover:underline"
        >
          {expanded ? "Hide clinical details" : "Show clinical details"}
        </button>
      ) : null}
    </div>
  );
}

/**
 * Split a paragraph on sentence boundaries (`. ` followed by an uppercase
 * letter or digit). Leaves abbreviations like "e.g." and decimals like "1.5"
 * intact. Used by RationaleBody to stage the first sentence above the fold.
 */
function splitSentences(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  // Lookbehind for `.` + space + capital-letter-or-digit start of next clause.
  const parts = trimmed.split(/(?<=[.!?])\s+(?=[A-Z0-9])/);
  return parts.map((p) => p.trim()).filter(Boolean);
}
