"use client";

import { useState } from "react";
import { AlertTriangle, ArrowRight, FlaskConical, HelpCircle } from "lucide-react";

import { Brca1FunctionCard } from "./Brca1FunctionCard";
import { CurrentDrugAssessmentCard } from "./CurrentDrugAssessmentCard";
import { DoctorVisitPdfButton } from "./DoctorVisitPdfButton";
import { HrdCard } from "./HrdCard";
import { MolViewer } from "./MolViewer";
import type { AnalysisResult, DemoPatient, SuggestedDrug } from "@/lib/bc-types";

interface Props {
  result: AnalysisResult;
  // When present, the report is framed around this preset patient (Maya, Diana,
  // Priya). When absent, the report is a generic "your query" layout used by
  // the /build route.
  patient?: DemoPatient | null;
  // Called when the user clicks a suggested-drug chip. /build wires this to
  // re-run the analysis with the new drug; the demo route just ignores it.
  onSwitchDrug?: (drugId: string) => void;
}

export function ResultsReport({ result, patient, onSwitchDrug }: Props) {
  return (
    <div className="space-y-6">
      {result.relevance_warning ? (
        <RelevanceWarning
          warning={result.relevance_warning}
          suggestions={result.suggested_drugs}
          onSwitchDrug={onSwitchDrug}
        />
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 md:gap-8">
        <div className="lg:col-span-2 space-y-6 md:space-y-8">
          <div className="no-print">
            <MolecularCard result={result} />
          </div>
          <WhatYouSeeCard result={result} />
        </div>

        <div className="lg:col-span-3 space-y-6 md:space-y-8">
          {result.hrd ? <HrdCard hrd={result.hrd} /> : null}

          {result.current_drug_assessment ? (
            <CurrentDrugAssessmentCard
              assessment={result.current_drug_assessment}
              onSwitchDrug={onSwitchDrug}
            />
          ) : null}

          <div className="no-print">
            <DoctorVisitPdfButton
              result={result}
              patientLabel={patient?.persona_name ?? null}
            />
          </div>

          {result.classifiable_brca1_variants.length > 0 ? (
            <Brca1FunctionSection hgvsList={result.classifiable_brca1_variants} />
          ) : null}
        </div>
      </div>
    </div>
  );
}

function RelevanceWarning({
  warning,
  suggestions,
  onSwitchDrug,
}: {
  warning: string;
  suggestions: SuggestedDrug[];
  onSwitchDrug?: (drugId: string) => void;
}) {
  return (
    <div
      className="border rounded-2xl p-5 md:p-6"
      style={{ background: "rgba(217,119,6,0.08)", borderColor: "rgba(217,119,6,0.35)" }}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 md:w-6 md:h-6 text-warning flex-shrink-0 mt-0.5" aria-hidden />
        <div className="space-y-3 flex-1 min-w-0">
          <div>
            <h3 className="font-semibold text-base md:text-lg mb-1">Heads up</h3>
            <p className="text-sm leading-relaxed">{warning}</p>
          </div>
          {suggestions.length > 0 ? (
            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Drugs that do involve your variants
              </p>
              <div className="flex flex-wrap gap-2">
                {suggestions.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => onSwitchDrug?.(s.id)}
                    disabled={!onSwitchDrug}
                    className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border bg-white text-sm hover:bg-accent transition-colors disabled:opacity-60 disabled:cursor-default"
                    title={s.reason}
                  >
                    <span className="font-medium">{s.name}</span>
                    <span className="text-xs text-muted-foreground">{s.reason}</span>
                    {onSwitchDrug ? <ArrowRight className="w-3.5 h-3.5" aria-hidden /> : null}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Tight explainer card paired with the 3D viewer: what the ribbons and
 * highlights in the image mean, in one short paragraph. */
function WhatYouSeeCard({ result }: { result: AnalysisResult }) {
  return (
    <div className="bg-card border rounded-2xl p-5 space-y-2">
      <h3 className="text-sm font-semibold">What you see in the 3D view</h3>
      <p className="text-sm leading-relaxed text-muted-foreground">
        {result.plain_language.what_you_see}
      </p>
    </div>
  );
}

function MolecularCard({ result }: { result: AnalysisResult }) {
  const [showHelp, setShowHelp] = useState(false);
  const pdbUrl = result.pose_pdb_url ?? result.protein_pdb_url;
  const highlights = result.pocket_residues.map((r) => ({
    position: r.position,
    inPocket: r.in_pocket,
  }));

  return (
    <div className="bg-card rounded-2xl overflow-hidden border">
      <div className="p-5 border-b space-y-2">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-lg font-semibold">
            {result.drug_name} binding to {result.target_gene}
          </h3>
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowHelp((v) => !v)}
              className="w-10 h-10 rounded-lg hover:bg-muted flex items-center justify-center"
              aria-label="What am I looking at?"
            >
              <HelpCircle className="w-5 h-5 text-muted-foreground" />
            </button>
            {showHelp ? (
              <div className="absolute right-0 top-11 z-30 w-72 bg-white border rounded-xl p-4 shadow-lg text-sm leading-relaxed">
                The grey ribbon is the protein in your cells. The bright shape is the drug
                positioned where it attaches. Yellow highlights are any variant residues you
                entered. Click and drag to rotate; scroll to zoom.
              </div>
            ) : null}
          </div>
        </div>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Zoomed in on the drug binding site. Rotate with click and drag, zoom with the scroll wheel.
        </p>
      </div>
      <div className="relative h-[440px]">
        <MolViewer pdbUrl={pdbUrl} highlights={highlights} />
        <div className="absolute top-2 left-2 bg-white/95 backdrop-blur-sm border rounded-md px-3 py-2 text-[11px] space-y-1 shadow-sm pointer-events-none">
          <div className="font-semibold text-muted-foreground uppercase tracking-wide text-[10px]">
            Legend
          </div>
          <LegendRow color="bg-slate-400" label="Protein (the drug's target)" />
          <LegendRow color="bg-pink-500" label="Drug molecule" />
          {highlights.length > 0 ? (
            <LegendRow color="bg-yellow-400" label="Your variant residue" />
          ) : null}
        </div>
      </div>
    </div>
  );
}

function LegendRow({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={`inline-block w-2.5 h-2.5 rounded-full ${color}`} aria-hidden />
      <span>{label}</span>
    </div>
  );
}

/**
 * "Predict the effect of my BRCA1 variant" — opt-in ML card.
 *
 * Collapsed by default because the prediction is experimental (XGBoost +
 * AlphaMissense ensemble, not a clinical classifier) and we don't want to
 * imply every patient should read it. Click the button to run.
 */
function Brca1FunctionSection({ hgvsList }: { hgvsList: string[] }) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <section className="bg-card border rounded-2xl p-5 flex items-center gap-4 flex-wrap">
        <FlaskConical className="w-5 h-5 text-primary flex-shrink-0" aria-hidden />
        <div className="flex-1 min-w-[200px]">
          <div className="text-base font-semibold">
            Predict BRCA1 variant effect{" "}
            <span className="text-xs font-normal text-muted-foreground">
              · experimental
            </span>
          </div>
          <div className="text-xs text-muted-foreground mt-0.5 font-mono truncate">
            {hgvsList.join(", ")}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex items-center justify-center rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Run prediction
        </button>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      {hgvsList.map((hgvs) => (
        <Brca1FunctionCard key={hgvs} hgvsProtein={hgvs} />
      ))}
    </div>
  );
}

