"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, HelpCircle, ShieldCheck } from "lucide-react";

import { api } from "@/lib/api";
import type {
  Brca1Classification,
  Brca1Label,
  BrcaExchangeRecord,
} from "@/lib/bc-types";

interface Props {
  hgvsProtein: string;
}

/**
 * BRCA1 variant-effect prediction, patient-facing.
 *
 * Deliberately renders WITHOUT an outer card wrapper so the parent
 * (HrdCard) can nest it as a subsection without creating a
 * card-inside-a-card. Technical details (conformal prediction set,
 * ensemble component scores, held-out model metrics) collapse behind
 * a single "Technical details" expander so the default view is the
 * plain-English takeaway: "the model thinks this variant breaks
 * BRCA1 → tumor expected to be HR-deficient → PARPi may work."
 */
export function Brca1FunctionCard({ hgvsProtein }: Props) {
  const classification = useQuery<Brca1Classification>({
    queryKey: ["brca1", hgvsProtein],
    queryFn: () => api.classifyBrca1(hgvsProtein),
    retry: 1,
  });
  // Expert-panel lookup runs in parallel and fails gracefully — BRCA Exchange
  // returning null means "no ENIGMA record found", not an error.
  const exchange = useQuery<BrcaExchangeRecord | null>({
    queryKey: ["brca1-exchange", hgvsProtein],
    queryFn: () => api.lookupBrcaExchange(hgvsProtein),
    retry: 0,
    staleTime: 60_000,
  });

  if (classification.isLoading) {
    return (
      <div className="text-sm text-muted-foreground">
        Predicting HR function for {hgvsProtein}…
      </div>
    );
  }
  if (classification.isError) {
    return (
      <div className="text-sm text-red-700">
        Couldn&apos;t classify {hgvsProtein}:{" "}
        {(classification.error as Error).message}
      </div>
    );
  }
  if (!classification.data) return null;

  const data = classification.data;
  const cfg = labelStyle(data.label);
  const pct = Math.round(data.probability_loss_of_function * 100);

  // Compact result format that matches the Tumor-scar tile in HrdCard:
  // colored headline row with the score on the right, and one "Details"
  // expander hiding the variant, plain-English explanation, expert-panel
  // line, conformal box, ensemble breakdown, model provenance, caveats.
  return (
    <div className={`rounded-lg border p-3 text-sm ${cfg.resultBox}`}>
      <div className="flex items-baseline justify-between gap-2 flex-wrap">
        <span className="font-semibold">{cfg.title}</span>
        <span className="text-xs">{pct}% p(LoF)</span>
      </div>
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer opacity-80 hover:opacity-100">
          Details
        </summary>
        <div className="mt-2 space-y-3">
          <div>
            <span className="font-mono text-xs">{data.hgvs_protein}</span>
            <p className="mt-1 leading-relaxed">{cfg.plain}</p>
            <p className="mt-1 opacity-80">
              <strong>{data.confidence}</strong> confidence
              {!data.in_assayed_region ? (
                <span className="text-warning">
                  {" "}
                  · outside training region
                </span>
              ) : null}
            </p>
          </div>
          {exchange.data ? (
            <ExpertClassificationLine
              record={exchange.data}
              hgvsProtein={hgvsProtein}
            />
          ) : null}
          <DomainLine data={data} />
          <ConformalBox data={data} />
          <EnsembleBreakdown data={data} />
          <ModelProvenance data={data} />
          <Caveats
            items={data.caveats}
            hasExpertClassification={!!exchange.data}
          />
        </div>
      </details>
    </div>
  );
}

function DomainLine({ data }: { data: Brca1Classification }) {
  return (
    <div className="text-xs text-muted-foreground">
      The mutated residue sits in the{" "}
      <strong>{domainLabel(data.domain)}</strong> region of BRCA1 (a{" "}
      {data.consequence.toLowerCase()} change, meaning one amino acid
      was swapped rather than a deletion or stop codon).
    </div>
  );
}

function ExpertClassificationLine({
  record,
  hgvsProtein,
}: {
  record: BrcaExchangeRecord;
  hgvsProtein: string;
}) {
  const cls = (record.enigma_classification ?? "").toLowerCase();
  const severity: "pathogenic" | "benign" | "vus" | "other" =
    cls.includes("pathogenic") ? "pathogenic"
      : cls.includes("benign") ? "benign"
      : cls.includes("uncertain") ? "vus"
      : "other";

  const styles = {
    pathogenic: "bg-red-50 border-red-300 text-red-900",
    benign: "bg-green-50 border-green-300 text-green-900",
    vus: "bg-amber-50 border-amber-300 text-amber-900",
    other: "bg-slate-50 border-slate-300 text-foreground",
  }[severity];

  return (
    <div className={`rounded-xl border p-3 ${styles} space-y-1`}>
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide font-semibold">
        <ShieldCheck className="w-3.5 h-3.5" aria-hidden />
        Expert panel (ENIGMA)
      </div>
      <div className="flex items-baseline gap-2 flex-wrap text-sm">
        <span className="font-semibold">
          {record.enigma_classification ?? "unknown"}
        </span>
        <span className="font-mono text-xs">{hgvsProtein}</span>
      </div>
      <p className="text-xs leading-relaxed opacity-90">
        Reviewed by clinicians and geneticists. When the expert panel
        disagrees with our ML model, trust the panel.
      </p>
      {record.link ? (
        <a
          href={record.link}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block text-xs underline hover:opacity-80"
        >
          View full record on BRCA Exchange →
        </a>
      ) : null}
    </div>
  );
}

function ConformalBox({ data }: { data: Brca1Classification }) {
  const c = data.conformal;
  const pct = Math.round(c.coverage * 100);
  const label =
    c.label === "loss_of_function" ? "Loss of function"
      : c.label === "functional" ? "Functional"
      : "Uncertain";
  const color =
    c.label === "loss_of_function" ? "text-red-700 bg-red-50 border-red-200"
      : c.label === "functional" ? "text-success bg-green-50 border-green-200"
      : "text-amber-700 bg-amber-50 border-amber-200";

  return (
    <div className={`border rounded-xl p-3 ${color}`}>
      <div className="text-[10px] uppercase tracking-wide font-semibold">
        Calibrated uncertainty at {pct}% coverage
      </div>
      <div className="font-semibold text-sm mt-0.5">{label}</div>
      <div className="text-xs mt-1 opacity-90">
        {c.label === "uncertain"
          ? `At the ${pct}% coverage guarantee the model can't narrow it down to a single answer. Both "loss of function" and "functional" remain plausible.`
          : `Conformal prediction is a calibration method: across similar variants, the true answer lands in the prediction set at least ${pct}% of the time. Here the set contains only one label, so the call is unambiguous at this coverage.`}
      </div>
    </div>
  );
}

function EnsembleBreakdown({ data }: { data: Brca1Classification }) {
  const c = data.components;
  const p = data.probability_loss_of_function;
  const am = c.alphamissense_score;
  return (
    <div className="text-xs bg-slate-50 rounded-lg border p-4 space-y-3">
      <div className="font-medium text-sm">Model ensemble</div>
      <p className="text-[11px] text-muted-foreground">
        Two separate models score this variant independently; a third
        meta-learner combines them. Each number is the probability that model
        assigns to &ldquo;loss of function&rdquo;.
      </p>
      <div className="grid grid-cols-3 gap-2">
        <ScoreBox
          label="XGBoost"
          value={c.xgb_probability.toFixed(3)}
          hint="trained on Findlay 2018 SGE"
        />
        <ScoreBox
          label="AlphaMissense"
          value={c.alphamissense_covered && am !== null ? am.toFixed(3) : "n/a"}
          hint={
            c.alphamissense_covered
              ? c.alphamissense_class ?? ""
              : "no score for this variant"
          }
        />
        <ScoreBox
          label="Ensemble"
          value={p.toFixed(3)}
          hint="logistic meta-learner"
          emphasize
        />
      </div>
      {!c.alphamissense_covered ? (
        <p className="text-[11px] text-muted-foreground">
          AlphaMissense doesn&apos;t score this change. The ensemble imputed
          its input with the training-set mean, so the XGBoost signal carries
          more weight here.
        </p>
      ) : null}
    </div>
  );
}

function ScoreBox({
  label,
  value,
  hint,
  emphasize,
}: {
  label: string;
  value: string;
  hint: string;
  emphasize?: boolean;
}) {
  return (
    <div
      className={`rounded border p-2 ${
        emphasize ? "bg-primary/5 border-primary/30" : "bg-white"
      }`}
    >
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="font-mono text-sm font-medium">{value}</div>
      <div className="text-[11px] text-muted-foreground truncate" title={hint}>
        {hint}
      </div>
    </div>
  );
}

function ModelProvenance({ data }: { data: Brca1Classification }) {
  return (
    <div className="text-xs bg-slate-50 rounded-lg p-4 space-y-2 border">
      <div className="font-medium text-sm">About this prediction</div>
      <p className="leading-relaxed">
        Trained on functional scores from{" "}
        <span className="italic">{data.training_citation}</span>
      </p>
      <div className="grid grid-cols-2 gap-2">
        <MetricBox
          label="Held-out AUROC"
          value={data.holdout_auroc.toFixed(3)}
          hint="how well the model separates broken from working variants on data it never saw during training"
        />
        <MetricBox
          label="Held-out AUPRC"
          value={data.holdout_auprc.toFixed(3)}
          hint="precision-recall area (positive class = broken)"
        />
      </div>
    </div>
  );
}

function MetricBox({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="bg-white rounded border p-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="font-mono text-sm font-medium">{value}</div>
      <div className="text-[11px] text-muted-foreground">{hint}</div>
    </div>
  );
}

function Caveats({
  items,
  hasExpertClassification,
}: {
  items: string[];
  hasExpertClassification?: boolean;
}) {
  return (
    <div className="border-l-4 border-warning bg-amber-50/50 rounded-r p-3 text-xs space-y-1">
      <div className="font-semibold flex items-center gap-1">
        <HelpCircle className="w-3.5 h-3.5" aria-hidden />
        Read these first
      </div>
      <ul className="list-disc ml-4 space-y-0.5">
        {hasExpertClassification ? (
          <li>
            An expert panel classification exists (shown above). When it
            disagrees with this prediction, trust the expert panel.
          </li>
        ) : null}
        {items.map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ul>
    </div>
  );
}

function labelStyle(label: Brca1Label): {
  title: string;
  plain: string;
  Icon: typeof CheckCircle2;
  color: string;
  bg: string;
  // Tailwind classes for the result box. Same shape as the scar-tile
  // label styles in HrdCard so the three lab tiles share visual rhythm
  // (text-foo bg-foo-10 border-foo-40).
  resultBox: string;
} {
  switch (label) {
    case "likely_loss_of_function":
      return {
        title: "Likely breaks BRCA1",
        plain:
          "Predicted to disable BRCA1's DNA-repair role — the signal PARP inhibitors target.",
        Icon: AlertCircle,
        color: "text-red-700",
        bg: "bg-red-50",
        resultBox: "text-success bg-success/10 border-success/40",
      };
    case "likely_functional":
      return {
        title: "Likely keeps BRCA1 working",
        plain:
          "Predicted to preserve BRCA1 function. PARP inhibitors unlikely to help here.",
        Icon: CheckCircle2,
        color: "text-success",
        bg: "bg-green-50",
        resultBox: "text-muted-foreground bg-muted border-border",
      };
    case "uncertain":
      return {
        title: "Can't call it yet",
        plain:
          "Model confidence too low to call. Variant of Uncertain Significance (VUS).",
        Icon: HelpCircle,
        color: "text-amber-700",
        bg: "bg-amber-50",
        resultBox: "text-warning bg-warning/10 border-warning/40",
      };
  }
}

function domainLabel(d: string): string {
  // Human-readable mapping for the compact domain codes in the catalog.
  const labels: Record<string, string> = {
    RING: "RING (one of BRCA1's active regions, at the N-terminus)",
    CoiledCoil: "coiled-coil (protein-binding segment)",
    BRCT1: "BRCT1 (C-terminal binding domain)",
    BRCT2: "BRCT2 (C-terminal binding domain)",
    BRCT_linker: "BRCT linker",
    Linker1: "central linker",
    Linker2: "BRCT-proximal linker",
    outside_assayed_domains: "region outside the training assay",
  };
  return labels[d] ?? d;
}
