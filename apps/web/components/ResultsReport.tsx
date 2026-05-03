"use client";

import { useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
} from "lucide-react";

import { HrdCard, type RecordRefs } from "./HrdCard";
import { MolViewer } from "./MolViewer";
import { VolumeViewer } from "./VolumeViewer";
import type {
  AnalysisResult,
  DemoPatient,
  OffTargetStructure,
  SuggestedDrug,
} from "@/lib/bc-types";

interface Props {
  result: AnalysisResult;
  // When present, the report is framed around this preset patient (Maya, Diana,
  // Priya). When absent, the report is a generic "your query" layout used by
  // the /build route.
  patient?: DemoPatient | null;
  // Called when the user clicks a suggested-drug chip. /build wires this to
  // re-run the analysis with the new drug; the demo route just ignores it.
  onSwitchDrug?: (drugId: string) => void;
  /**
   * /build users who uploaded their own CT scan can pass a blob URL here so
   * the slideshow + radiogenomics panel target the user-uploaded volume
   * instead of (or in addition to) the per-patient demo fixture.
   */
  uploadedCtScanUrl?: string | null;
  /**
   * Pre-parsed tumor-scar numbers from a patient's stored report file
   * (LOH / LST / NtAI). Threaded down to HrdCard's scar panel so it
   * auto-runs the score instead of waiting for the user to type the
   * numbers in.
   */
  scarPrefill?: { loh: number; lst: number; ntai: number } | null;
  /**
   * Filenames of the patient's uploaded records, surfaced inside each
   * lab-tile so the patient can trace which file drives which model.
   */
  recordRefs?: RecordRefs;
}

export function ResultsReport({
  result,
  patient,
  onSwitchDrug,
  uploadedCtScanUrl,
  scarPrefill,
  recordRefs,
}: Props) {
  // Per-patient radiogenomics fixture wiring.
  //   Maya  — pelvic CT (TCGA-24-0975) — supports her HR-deficient germline
  //           call. Model: p(HRD) ~0.97 (green).
  //   Diana — staging CT (TCGA-25-1314) — somatic-HRD pre-screen story.
  //           Model: p(HRD) ~0.91 (green).
  //   Priya — no CT. Real breast cancer patients are imaged with MG/MRI,
  //           not CT, and TCGA-BRCA on TCIA has no CT modality. Her HRD
  //           evidence is the BRCA2 germline variant + tumor scar score.
  // /build users who uploaded their own CT scan override the lookup with
  // the blob URL of their upload.
  const ctScanUrl =
    uploadedCtScanUrl ??
    (patient?.id === "maya"
      ? "/fixtures/maya_ct_scan.nii.gz"
      : patient?.id === "diana"
        ? "/fixtures/diana_ct_scan.nii.gz"
        : null);
  const ctScanLabel = uploadedCtScanUrl
    ? "Your uploaded CT"
    : patient?.id === "maya"
      ? "Maya's pelvic CT"
      : patient?.id === "diana"
        ? "Diana's staging CT"
        : null;

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
        {/* Left column: slideshow only — just the visuals (drug on target,
            patient variant, CT volume render). Narrower (2/5) so the
            slideshow square stays compact and the right-column report
            gets the bulk of the page. */}
        <div className="lg:col-span-2 no-print">
          <StructureSlideshow
            result={result}
            ctScanVolumeUrl={ctScanUrl}
            ctScanLabel={ctScanLabel}
          />
        </div>

        {/* Right column: HRD result first, then the drug-match verdict
            ("Olaparib is explicitly endorsed for your variants"), then
            the doctor-visit PDF as the closing action. */}
        <div className="lg:col-span-3 space-y-6 md:space-y-8">
          {result.hrd ? (
            <HrdCard
              hrd={result.hrd}
              classifiableBrca1Variants={result.classifiable_brca1_variants}
              drugId={result.drug_id}
              ctScanUrl={ctScanUrl}
              ctScanLabel={ctScanLabel}
              scarPrefill={scarPrefill}
              recordRefs={recordRefs}
              analysisResult={result}
              patientLabel={patient?.persona_name ?? null}
            />
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

/**
 * Single 3D card that shows the drug-on-target view, every per-variant
 * protein view, and (when available) the patient's preoperative CT scan
 * in one place, swappable with arrows at the top. The card size + chrome
 * stay constant so the left column doesn't reflow when flipping views.
 */
function StructureSlideshow({
  result,
  ctScanVolumeUrl,
  ctScanLabel,
}: {
  result: AnalysisResult;
  ctScanVolumeUrl?: string | null;
  ctScanLabel?: string | null;
}) {
  // Each "slide" is either the docked drug + target (kind="main"), a
  // single off-target protein with its variant residue highlighted
  // (kind="off_target"), or the patient's CT scan (kind="ct_scan"). The
  // CT slide renders the full 3D volume via niivue (WebGL2 ray-marching)
  // on the same .nii.gz the HrdCard's "Run model" button scores.
  type Slide =
    | { kind: "main" }
    | { kind: "off_target"; structure: OffTargetStructure }
    | { kind: "ct_scan"; volumeUrl: string; label: string };

  const slides: Slide[] = [
    { kind: "main" },
    ...(result.off_target_structures ?? []).map(
      (s): Slide => ({ kind: "off_target", structure: s }),
    ),
    ...(ctScanVolumeUrl
      ? [
          {
            kind: "ct_scan" as const,
            volumeUrl: ctScanVolumeUrl,
            label: ctScanLabel ?? "Preoperative CT",
          },
        ]
      : []),
  ];
  const [idx, setIdx] = useState(0);
  const clamped = Math.min(idx, slides.length - 1);
  const slide = slides[clamped];
  const total = slides.length;

  const titleFor = (s: Slide) => {
    if (s.kind === "main")
      return `${result.drug_name} binding to ${result.target_gene}`;
    if (s.kind === "off_target") return `Your variant on ${s.structure.gene_symbol}`;
    return s.label;
  };

  // Square aspect. Width = column width (the column is now the narrower
  // 2/5 of the page) so the card stays compact without an explicit
  // max-w cap; aspect-square enforces a true square. overflow-hidden
  // absorbs inner viewer/header variance so cycling slides never reflows.
  return (
    <div className="bg-card rounded-2xl overflow-hidden border flex flex-col aspect-square w-full">
      {total > 1 ? (
        <div className="flex items-center gap-2 px-3 py-2 border-b bg-muted/40">
          <button
            type="button"
            onClick={() => setIdx((i) => (i - 1 + total) % total)}
            className="p-1.5 rounded-md hover:bg-white/80 transition-colors"
            aria-label="Previous view"
          >
            <ChevronLeft className="w-4 h-4" aria-hidden />
          </button>
          <div className="flex-1 text-center text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{titleFor(slide)}</span>
            <span className="mx-2 text-muted-foreground/70">·</span>
            {clamped + 1} of {total}
          </div>
          <button
            type="button"
            onClick={() => setIdx((i) => (i + 1) % total)}
            className="p-1.5 rounded-md hover:bg-white/80 transition-colors"
            aria-label="Next view"
          >
            <ChevronRight className="w-4 h-4" aria-hidden />
          </button>
        </div>
      ) : null}
      <div className="flex-1 flex flex-col overflow-hidden">
        {slide.kind === "main" ? (
          <MolecularCard result={result} hideOuterBorder />
        ) : slide.kind === "off_target" ? (
          <OffTargetStructureCard
            structure={slide.structure}
            hideOuterBorder
          />
        ) : (
          <CtScanSlide volumeUrl={slide.volumeUrl} label={slide.label} />
        )}
      </div>
      {total > 1 ? (
        <div className="flex justify-center gap-1.5 pb-3 pt-1">
          {slides.map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setIdx(i)}
              aria-label={`Go to view ${i + 1}`}
              className={`w-1.5 h-1.5 rounded-full transition-colors ${
                i === clamped ? "bg-primary" : "bg-muted-foreground/30"
              }`}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Patient's preoperative CT scan shown as a single axial slice. This is
 * the image the radiogenomics model scores from; actually running the
 * model is the job of the `RadiogenomicsCtPanel` button inside the
 * HrdCard on the right column, so the two reinforce each other
 * visually — "this is the picture, here's what the model says about it".
 */
function CtScanSlide({ volumeUrl, label }: { volumeUrl: string; label: string }) {
  return (
    <div className="flex-1 flex flex-col">
      <div className="p-5 border-b space-y-1">
        <h3 className="text-lg font-semibold">{label}</h3>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Real preoperative pelvic CT from a TCGA-OV patient.
        </p>
      </div>
      <div className="relative bg-black flex-1 min-h-0">
        <VolumeViewer volumeUrl={volumeUrl} />
      </div>
    </div>
  );
}

function MolecularCard({
  result,
  hideOuterBorder = false,
}: {
  result: AnalysisResult;
  hideOuterBorder?: boolean;
}) {
  const [showHelp, setShowHelp] = useState(false);
  const pdbUrl = result.pose_pdb_url ?? result.protein_pdb_url;
  const highlights = result.pocket_residues.map((r) => ({
    position: r.position,
    inPocket: r.in_pocket,
  }));

  const shell = hideOuterBorder
    ? "bg-transparent flex-1 flex flex-col"
    : "bg-card rounded-2xl overflow-hidden border";

  return (
    <div className={shell}>
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
                positioned where it attaches. Pink highlights are any variant residues you
                entered. Click and drag to rotate; scroll to zoom.
              </div>
            ) : null}
          </div>
        </div>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Drug bound to its target protein.
        </p>
      </div>
      <div className="relative flex-1 min-h-0">
        <MolViewer pdbUrl={pdbUrl} highlights={highlights} />
        <div className="absolute top-2 left-2 bg-white/95 backdrop-blur-sm border rounded-md px-3 py-2 text-[11px] space-y-1 shadow-sm pointer-events-none">
          <div className="font-semibold text-muted-foreground uppercase tracking-wide text-[10px]">
            Legend
          </div>
          <LegendRow color="bg-slate-400" label="Protein (the drug's target)" />
          <LegendRow color="bg-pink-500" label="Drug molecule" />
          {highlights.length > 0 ? (
            <LegendRow color="bg-pink-500" label="Your variant residue" />
          ) : null}
        </div>
      </div>
    </div>
  );
}

/**
 * 3D view for a gene the patient has a variant in that's NOT the drug's
 * primary target — e.g. Maya's BRCA1 p.Cys61Gly rendered on BRCA1's
 * AlphaFold structure, separate from the PARP1 + olaparib view above.
 *
 * No drug ligand here (there's no docked pose — this isn't where the
 * drug binds), just the protein with the variant residue highlighted
 * so the patient can actually see where their mutation sits.
 */
function OffTargetStructureCard({
  structure,
  hideOuterBorder = false,
}: {
  structure: OffTargetStructure;
  hideOuterBorder?: boolean;
}) {
  const highlights = structure.positions.map((p) => ({
    position: p,
    inPocket: false,
  }));
  const variantSummary = structure.variant_labels.join(", ");

  // Trailing protein-name phrase ("...sits on Breast cancer type 1
  // susceptibility protein.") was confusing on the ovarian-cancer pages —
  // it's the UniProt name for BRCA1 (the gene was first discovered in
  // breast cancer), not a description of the patient's cancer. Use the
  // gene SYMBOL instead so the sentence reads cleanly on every patient.
  const headerBody =
    structure.unavailable_reason ? (
      <p className="text-sm text-muted-foreground leading-relaxed">
        <span className="font-mono text-xs">{variantSummary}</span> sits on{" "}
        {structure.gene_symbol}.
      </p>
    ) : (
      <p className="text-sm text-muted-foreground leading-relaxed">
        The pink residue{highlights.length === 1 ? "" : "s"} mark
        {highlights.length === 1 ? "s" : ""} where{" "}
        <span className="font-mono text-xs">{variantSummary}</span> sits on{" "}
        {structure.gene_symbol}.
      </p>
    );

  const shell = hideOuterBorder
    ? "bg-transparent flex-1 flex flex-col"
    : "bg-card rounded-2xl overflow-hidden border";

  return (
    <div className={shell}>
      <div className="p-5 border-b space-y-1">
        <h3 className="text-lg font-semibold">
          Your variant on {structure.gene_symbol}
        </h3>
        {headerBody}
      </div>
      {structure.unavailable_reason ? (
        <div className="p-5 md:p-6 text-sm text-muted-foreground leading-relaxed bg-muted/40">
          {structure.unavailable_reason}
        </div>
      ) : (
        <div className="relative flex-1 min-h-0">
          <MolViewer
            key={structure.protein_pdb_url}
            pdbUrl={structure.protein_pdb_url}
            highlights={highlights}
          />
          <div className="absolute top-2 left-2 bg-white/95 backdrop-blur-sm border rounded-md px-3 py-2 text-[11px] space-y-1 shadow-sm pointer-events-none">
            <div className="font-semibold text-muted-foreground uppercase tracking-wide text-[10px]">
              Legend
            </div>
            <LegendRow color="bg-slate-400" label={structure.gene_symbol} />
            {highlights.length > 0 ? (
              <LegendRow color="bg-pink-500" label="Your variant residue" />
            ) : null}
          </div>
        </div>
      )}
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

