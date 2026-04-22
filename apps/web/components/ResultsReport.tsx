"use client";

import { useState } from "react";
import { AlertTriangle, ArrowRight, ChevronDown, Copy, HelpCircle, Printer } from "lucide-react";

import { Brca1FunctionCard } from "./Brca1FunctionCard";
import { MolViewer } from "./MolViewer";
import { StatusBadge, type PatientStatus } from "./StatusBadge";
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
  const status = patient ? patient.status : headlineToStatus(result.headline_severity);

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
        <div className="lg:col-span-2 lg:sticky lg:top-6 lg:h-fit no-print">
          <MolecularCard result={result} />
        </div>

        <div className="lg:col-span-3 space-y-6 md:space-y-8">
          <StatusBadge status={status}>{result.headline}</StatusBadge>
          {result.classifiable_brca1_variants.length > 0
            ? result.classifiable_brca1_variants.map((hgvs) => (
                <Brca1FunctionCard key={hgvs} hgvsProtein={hgvs} />
              ))
            : null}
          <WhatThisMeansCard result={result} />
          <QuestionsCard result={result} patient={patient} />
          <HowWeKnowCard result={result} />
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

function headlineToStatus(
  severity: AnalysisResult["headline_severity"],
): PatientStatus {
  if (severity === "benefit" || severity === "info") return "expected";
  if (severity === "caution") return "reduced";
  return "dose-adjustment";
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

function WhatThisMeansCard({ result }: { result: AnalysisResult }) {
  const pl = result.plain_language;
  return (
    <div className="bg-card border rounded-2xl p-6 md:p-8 space-y-4">
      <h2 className="text-xl md:text-2xl font-semibold">What this means</h2>
      <Para>{pl.what_you_see}</Para>
      <Para>{pl.how_the_drug_works}</Para>
      <Para>{pl.what_it_means_for_you}</Para>
    </div>
  );
}

function Para({ children }: { children: React.ReactNode }) {
  return <p className="leading-relaxed text-[15px]">{children}</p>;
}

function QuestionsCard({
  result,
  patient,
}: {
  result: AnalysisResult;
  patient?: DemoPatient | null;
}) {
  const questions = result.plain_language.questions_to_ask;

  function onCopy() {
    const text = questions.map((q, i) => `${i + 1}. ${q}`).join("\n");
    navigator.clipboard?.writeText(text);
  }

  function onPrint() {
    window.print();
  }

  const tailoredTo = patient ? `${patient.persona_name}'s` : "your";

  return (
    <div className="bg-card border rounded-2xl p-6 md:p-8 space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-xl md:text-2xl font-semibold">Questions to ask your doctor</h2>
        <div className="flex gap-2 no-print">
          <button
            onClick={onCopy}
            className="inline-flex items-center gap-2 px-4 py-2 bg-muted hover:bg-accent rounded-lg transition-colors"
            aria-label="Copy questions to clipboard"
          >
            <Copy className="w-4 h-4" aria-hidden />
            <span className="text-sm">Copy</span>
          </button>
          <button
            onClick={onPrint}
            className="inline-flex items-center gap-2 px-4 py-2 bg-muted hover:bg-accent rounded-lg transition-colors"
            aria-label="Print questions for appointment"
          >
            <Printer className="w-4 h-4" aria-hidden />
            <span className="text-sm">Print</span>
          </button>
        </div>
      </div>
      <ul className="space-y-4 questions-list">
        {questions.map((q, i) => (
          <li key={i} className="flex gap-3">
            <span className="text-primary flex-shrink-0">{i + 1}.</span>
            <span className="leading-relaxed">{q}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground pt-2 border-t">
        This list is tailored to {tailoredTo} genotype and drug. Bring it, printed or on your
        phone, to your next appointment.
      </p>
    </div>
  );
}

function HowWeKnowCard({ result }: { result: AnalysisResult }) {
  const [open, setOpen] = useState(false);
  const hw = result.plain_language.how_we_know;

  return (
    <div className="bg-card border rounded-2xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full px-6 md:px-8 py-5 flex items-center justify-between hover:bg-muted/50 transition-colors text-left"
      >
        <h2 className="text-xl md:text-2xl font-semibold">How we know this</h2>
        <ChevronDown
          className={`w-5 h-5 md:w-6 md:h-6 text-muted-foreground transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>
      {open ? (
        <div className="border-t px-6 md:px-8 py-5 space-y-4">
          <div>
            <h3 className="font-medium mb-1">Source</h3>
            <a
              href={hw.link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline text-sm break-all"
            >
              {hw.source}
            </a>
          </div>
          <div>
            <h3 className="font-medium mb-1">Evidence summary</h3>
            <p className="leading-relaxed text-muted-foreground text-sm">{hw.summary}</p>
          </div>
          {result.pgx_verdicts.length > 0 ? (
            <div>
              <h3 className="font-medium mb-2">Matched guidance</h3>
              <ul className="space-y-2 text-sm">
                {result.pgx_verdicts.map((v, i) => (
                  <li key={i} className="border rounded p-3 bg-white">
                    <div className="flex items-baseline justify-between gap-2 flex-wrap">
                      <span className="font-medium">{v.phenotype}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                        Evidence {v.evidence_level}
                      </span>
                    </div>
                    <div className="text-muted-foreground mt-1">{v.recommendation}</div>
                    <div className="text-xs italic mt-1 text-muted-foreground">{v.source}</div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
