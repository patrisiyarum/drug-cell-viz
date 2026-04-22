"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, HelpCircle, ShieldCheck, Sparkles } from "lucide-react";

import { api } from "@/lib/api";
import type {
  Brca1Classification,
  Brca1Label,
  BrcaExchangeRecord,
} from "@/lib/bc-types";

interface Props {
  hgvsProtein: string;
}

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
    return <Shell>Predicting HR function for {hgvsProtein}…</Shell>;
  }
  if (classification.isError) {
    return (
      <Shell>
        <p className="text-sm text-red-700">
          Couldn't classify {hgvsProtein}:{" "}
          {(classification.error as Error).message}
        </p>
      </Shell>
    );
  }
  if (!classification.data) return null;

  return (
    <div className="space-y-4">
      {exchange.data ? (
        <ExpertClassificationCard record={exchange.data} hgvsProtein={hgvsProtein} />
      ) : null}

      <div className="bg-card border rounded-2xl overflow-hidden">
        <div className="px-5 md:px-6 py-4 border-b flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-primary" aria-hidden />
          <h2 className="text-lg md:text-xl font-semibold">
            HR function prediction (experimental)
          </h2>
        </div>

        <div className="px-5 md:px-6 py-5 space-y-5">
          <Verdict data={classification.data} />
          <ConformalBox data={classification.data} />
          <EnsembleBreakdown data={classification.data} />
          <ModelProvenance data={classification.data} />
          <Caveats
            items={classification.data.caveats}
            hasExpertClassification={!!exchange.data}
          />
        </div>
      </div>
    </div>
  );
}

function ExpertClassificationCard({
  record,
  hgvsProtein,
}: {
  record: BrcaExchangeRecord;
  hgvsProtein: string;
}) {
  const cls = (record.enigma_classification ?? "").toLowerCase();
  const severity: "pathogenic" | "benign" | "vus" | "other" =
    cls.includes("pathogenic") && !cls.includes("likely pathogenic")
      ? "pathogenic"
      : cls.includes("likely pathogenic")
      ? "pathogenic"
      : cls.includes("benign")
      ? "benign"
      : cls.includes("uncertain")
      ? "vus"
      : "other";

  const styles = {
    pathogenic: "bg-red-50 border-red-300",
    benign: "bg-green-50 border-green-300",
    vus: "bg-amber-50 border-amber-300",
    other: "bg-slate-50 border-slate-300",
  }[severity];

  return (
    <div className={`border rounded-2xl overflow-hidden ${styles}`}>
      <div className="px-5 md:px-6 py-4 border-b border-current/20 flex items-center gap-2">
        <ShieldCheck className="w-5 h-5" aria-hidden />
        <h2 className="text-lg md:text-xl font-semibold">
          Expert panel classification (BRCA Exchange / ENIGMA)
        </h2>
      </div>
      <div className="px-5 md:px-6 py-5 space-y-3 text-sm">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="font-semibold text-base md:text-lg">
            {record.enigma_classification ?? "unknown"}
          </span>
          <span className="font-mono text-xs">{hgvsProtein}</span>
          {record.hgvs_cdna ? (
            <span className="font-mono text-xs text-muted-foreground">
              {record.hgvs_cdna}
            </span>
          ) : null}
        </div>
        <p className="leading-relaxed">
          This variant has been reviewed by the ENIGMA consortium expert panel.
          This classification comes from clinicians and geneticists reviewing
          family, functional, and population evidence — it outranks the machine
          learning prediction shown below when they disagree.
        </p>
        {record.enigma_date_evaluated ? (
          <div className="text-xs text-muted-foreground">
            Last evaluated {record.enigma_date_evaluated}
            {record.enigma_method ? ` · method: ${record.enigma_method}` : ""}
          </div>
        ) : null}
        {record.link ? (
          <a
            href={record.link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block text-sm underline hover:opacity-80"
          >
            View full record on BRCA Exchange →
          </a>
        ) : null}
      </div>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-card border rounded-2xl px-5 md:px-6 py-5 space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="w-5 h-5 text-primary" aria-hidden />
        <h2 className="text-lg md:text-xl font-semibold">
          HR function prediction
        </h2>
      </div>
      <div className="text-sm text-muted-foreground">{children}</div>
    </div>
  );
}

function ConformalBox({ data }: { data: Brca1Classification }) {
  const c = data.conformal;
  const pct = Math.round(c.coverage * 100);
  const label =
    c.label === "loss_of_function"
      ? "Loss of function"
      : c.label === "functional"
      ? "Functional"
      : "Uncertain";
  const color =
    c.label === "loss_of_function"
      ? "text-red-700 bg-red-50 border-red-200"
      : c.label === "functional"
      ? "text-success bg-green-50 border-green-200"
      : "text-amber-700 bg-amber-50 border-amber-200";

  return (
    <div className={`border rounded-xl p-3 md:p-4 ${color}`}>
      <div className="text-[10px] uppercase tracking-wide font-semibold">
        At {pct}% confidence (conformal prediction)
      </div>
      <div className="font-semibold text-base md:text-lg mt-0.5">{label}</div>
      <div className="text-xs mt-1 opacity-90">
        {c.label === "uncertain"
          ? `At the ${pct}% coverage level the model can't distinguish this variant from both classes. Lower-confidence point estimate below.`
          : `The 80%-coverage prediction set is a singleton, so the model is confident in this call at this coverage.`}
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
      <div className="font-medium text-sm">Model ensemble (ensemble + AlphaMissense)</div>
      <div className="grid grid-cols-3 gap-2">
        <ScoreBox
          label="XGBoost"
          value={c.xgb_probability.toFixed(3)}
          hint="trained on Findlay SGE"
        />
        <ScoreBox
          label="AlphaMissense"
          value={
            c.alphamissense_covered && am !== null ? am.toFixed(3) : "—"
          }
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
          AlphaMissense doesn't score this change (synonymous / nonsense /
          outside its table). The ensemble imputed its input with the
          training-set mean, so the XGBoost signal carries more weight here.
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

function Verdict({ data }: { data: Brca1Classification }) {
  const cfg = labelStyle(data.label);
  const Icon = cfg.Icon;
  return (
    <div className={`rounded-xl p-4 md:p-5 ${cfg.bg}`}>
      <div className="flex items-start gap-3">
        <Icon className={`w-6 h-6 ${cfg.color} flex-shrink-0 mt-0.5`} aria-hidden />
        <div className="space-y-2 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="font-semibold text-base md:text-lg">{cfg.title}</span>
            <span className="font-mono text-sm">{data.hgvs_protein}</span>
            <span className="text-xs text-muted-foreground">
              probability loss-of-function: {(data.probability_loss_of_function * 100).toFixed(0)}%
              · confidence: {data.confidence}
            </span>
          </div>
          <p className="text-sm leading-relaxed">{cfg.explanation}</p>
          <div className="text-xs text-muted-foreground">
            Residue is in the <strong>{domainLabel(data.domain)}</strong> domain ·{" "}
            {data.consequence.toLowerCase()} change
            {data.in_assayed_region ? null : (
              <>
                {" "}
                ·{" "}
                <span className="text-warning font-medium">
                  outside assayed region (extrapolation)
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ModelProvenance({ data }: { data: Brca1Classification }) {
  return (
    <div className="text-xs bg-slate-50 rounded-lg p-4 space-y-2 border">
      <div className="font-medium text-sm">About this prediction</div>
      <p className="leading-relaxed">
        The model ({data.model_version}) was trained on functional scores from{" "}
        <span className="italic">{data.training_citation}</span>
      </p>
      <div className="grid grid-cols-2 gap-2">
        <MetricBox
          label="Held-out AUROC"
          value={data.holdout_auroc.toFixed(3)}
          hint="ability to separate LOF from FUNC variants"
        />
        <MetricBox
          label="Held-out AUPRC"
          value={data.holdout_auprc.toFixed(3)}
          hint="precision-recall curve area (positive = LOF)"
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
  explanation: string;
  Icon: typeof CheckCircle2;
  color: string;
  bg: string;
} {
  switch (label) {
    case "likely_loss_of_function":
      return {
        title: "Likely loss of function",
        explanation:
          "The model predicts this BRCA1 variant disrupts homologous-recombination repair. Tumors with this variant would be expected to be HR-deficient and therefore sensitive to PARP inhibitors like olaparib. This aligns with pathogenic classification in BRCA Exchange for known variants of this type.",
        Icon: AlertCircle,
        color: "text-red-700",
        bg: "bg-red-50",
      };
    case "likely_functional":
      return {
        title: "Likely functional",
        explanation:
          "The model predicts this variant preserves BRCA1 function. HR-proficient cells are not expected to be selectively sensitive to PARP inhibitors through synthetic lethality.",
        Icon: CheckCircle2,
        color: "text-success",
        bg: "bg-green-50",
      };
    case "uncertain":
      return {
        title: "Uncertain",
        explanation:
          "The model's confidence is low: the variant sits between clear functional and clear loss-of-function patterns it saw in training. Clinically, this is a Variant of Uncertain Significance (VUS). Clinical-grade functional testing or expert curation (ENIGMA) is the next step.",
        Icon: HelpCircle,
        color: "text-amber-700",
        bg: "bg-amber-50",
      };
  }
}

function domainLabel(d: string): string {
  // Human-readable mapping for the compact domain codes in the catalog.
  const labels: Record<string, string> = {
    RING: "RING (E3 ligase, N-terminal)",
    CoiledCoil: "coiled-coil",
    BRCT1: "BRCT1 (C-terminal, binds phospho-peptides)",
    BRCT2: "BRCT2 (C-terminal)",
    BRCT_linker: "BRCT linker",
    Linker1: "central linker",
    Linker2: "BRCT-proximal linker",
    outside_assayed_domains: "outside assayed domains",
  };
  return labels[d] ?? d;
}
