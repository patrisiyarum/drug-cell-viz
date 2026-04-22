"use client";

import type { CurrentDrugAssessment, PGxVerdict } from "@/lib/bc-types";

interface Props {
  drugName: string;
  assessment: CurrentDrugAssessment;
  // PGx verdicts get surfaced as a prominent "you are a [phenotype]" line at
  // the top of the card. This is the single most important takeaway in cases
  // like Diana's (CYP2D6*4 homozygous → poor metabolizer → tamoxifen won't
  // convert to endoxifen efficiently). Patients shouldn't have to infer that
  // from the rationale paragraph.
  pgxVerdicts?: PGxVerdict[];
  onSwitchDrug?: (drugId: string) => void;
}

/**
 * "Is my current drug right for me?" card — the second-opinion feature.
 *
 * For a patient who already knows their variants AND which drug they've been
 * prescribed, this card gives a one-sentence verdict (well matched / review
 * needed / etc) rather than making them parse CPIC rule text. Any strictly
 * better-matched drugs show as quick-switch chips.
 */
export function CurrentDrugAssessmentCard({
  drugName,
  assessment,
  pgxVerdicts,
  onSwitchDrug,
}: Props) {
  // Pick the most informative verdict to feature as the top-line metabolizer /
  // phenotype summary. Prefer the one that's about the drug the patient is on.
  const featured = (pgxVerdicts ?? []).find(
    (v) => v.drug_name.toLowerCase() === drugName.toLowerCase(),
  ) ?? pgxVerdicts?.[0];
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
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
            Is {drugName} the right drug for you?
          </div>
          <h3 className="text-lg md:text-xl font-semibold">
            {assessment.headline}
          </h3>
        </div>
        <div className={`px-3 py-1.5 rounded-full text-sm font-semibold ${style.pill}`}>
          {style.label}
        </div>
      </header>

      {featured ? (
        <div className="rounded-lg border-2 border-dashed p-3 md:p-4 bg-white/70 space-y-1">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Bottom line
          </div>
          <p className="text-sm md:text-base leading-relaxed">
            Your <span className="font-mono text-xs">{featured.variant_label}</span>{" "}
            ({featured.zygosity}) makes you a{" "}
            <span className="font-semibold">{featured.phenotype}</span>
            {phenotypeToAction(featured, drugName)}
          </p>
        </div>
      ) : (
        // Fall back to the full rationale only when we don't have a clean
        // one-liner to show. Keeps the card short in the common case.
        <p className="text-sm leading-relaxed">{assessment.rationale}</p>
      )}

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
 * Turn a PGx verdict into a one-clause action statement, e.g. ", so your
 * oncologist may consider an alternative hormonal therapy (aromatase
 * inhibitor)." Maps CPIC/FDA recommendation text into patient-facing prose.
 */
function phenotypeToAction(v: PGxVerdict, drugName: string): string {
  const rec = v.recommendation.toLowerCase();
  if (rec.includes("avoid")) {
    return `, so current guidance is to avoid ${drugName} at standard doses and consider an alternative.`;
  }
  if (rec.includes("alternative")) {
    return `, so your oncologist may consider an alternative to ${drugName}.`;
  }
  if (rec.includes("reduce") || rec.includes("50%")) {
    return `, so ${drugName} dose typically needs to be reduced to avoid toxicity.`;
  }
  if (rec.includes("higher") || rec.includes("40 mg")) {
    return `, so a higher ${drugName} dose may be considered (data strongest in premenopausal patients).`;
  }
  if (rec.includes("fda-approved") || rec.includes("eligibility") || rec.includes("eligible")) {
    return `, which is an FDA-recognized indication for ${drugName}.`;
  }
  return ".";
}
