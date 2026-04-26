"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { HelpCircle } from "lucide-react";

import type {
  AnalysisResult,
  Catalog,
  CatalogVariant,
  GeneEffectType,
  VariantInput,
  Zygosity,
} from "@/lib/bc-types";

/**
 * The /build page presents a 4-step flow: pick a drug, (optional) upload raw
 * data, select variants, see the report. Steps 1 and 3 both need to read and
 * write the same analysis state, so we split the old monolithic
 * BCAnalysisForm into a controlled hook + three render components. The /build
 * page calls useBCAnalysisForm() once and hands the handle to each of the
 * DrugPickerSection / VariantPickerSection / RunAnalysisButton placed inside
 * its numbered Step cards.
 */

const EFFECT_GROUP_ORDER: GeneEffectType[] = [
  "dna_repair",
  "drug_target",
  "drug_metabolism",
  "other",
];

const EFFECT_LABELS: Record<GeneEffectType, { title: string; blurb: string }> = {
  dna_repair: {
    title: "DNA repair genes",
    blurb:
      "Variants here affect how well cells fix DNA damage, which matters for drugs like olaparib that exploit broken DNA repair.",
  },
  drug_target: {
    title: "Drug target genes",
    blurb:
      "Variants here change the protein the drug is trying to bind. They can make drugs work better, worse, or not at all.",
  },
  drug_metabolism: {
    title: "Drug-processing genes",
    blurb:
      "Variants here change how your body activates or clears the drug, which affects the right dose for you.",
  },
  other: {
    title: "Other",
    blurb: "Variants in genes that don't fit the categories above.",
  },
};

interface SelectedVariant {
  catalog_id: string;
  zygosity: Zygosity;
}

interface HookProps {
  onResult: (
    result: AnalysisResult,
    context: { drugId: string; variants: VariantInput[] },
  ) => void;
  drugIdOverride?: string;
  presetVariants?: SelectedVariant[];
  /**
   * When true, the submit guard against an empty variants list is dropped.
   * Caller passes this in when they've satisfied the "need at least one
   * input" rule via a different surface — e.g. an uploaded CT scan that
   * the radiogenomics panel will score on the results page.
   */
  allowEmptyVariants?: boolean;
}

export interface BCAnalysisFormHandle {
  catalog: Catalog | undefined;
  isLoading: boolean;
  drugId: string;
  setDrugId: (id: string) => void;
  picked: SelectedVariant[];
  togglePicked: (variantId: string) => void;
  setZygosity: (variantId: string, z: Zygosity) => void;
  pastedGene: string;
  setPastedGene: (s: string) => void;
  pastedSeq: string;
  setPastedSeq: (s: string) => void;
  submitting: boolean;
  error: string | null;
  submit: () => Promise<void>;
}

export function useBCAnalysisForm({
  onResult,
  drugIdOverride,
  presetVariants,
  allowEmptyVariants,
}: HookProps): BCAnalysisFormHandle {
  const { data: catalog, isLoading } = useQuery<Catalog>({
    queryKey: ["bc-catalog"],
    queryFn: () => api.getCatalog(),
  });

  const [drugId, setDrugId] = useState<string>(drugIdOverride ?? "tamoxifen");
  useEffect(() => {
    if (drugIdOverride && drugIdOverride !== drugId) setDrugId(drugIdOverride);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drugIdOverride]);

  const [picked, setPicked] = useState<SelectedVariant[]>([
    { catalog_id: "CYP2D6_star4", zygosity: "homozygous" },
  ]);

  // Merge upload-detected variants into the picker without clobbering manual
  // selections. Runs whenever presetVariants changes — i.e. after a new
  // 23andMe or VCF file is parsed in Step 2.
  useEffect(() => {
    if (!presetVariants || presetVariants.length === 0) return;
    setPicked((cur) => {
      const byId = new Map(cur.map((p) => [p.catalog_id, p]));
      for (const p of presetVariants) byId.set(p.catalog_id, p);
      return Array.from(byId.values());
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(presetVariants)]);

  const [pastedGene, setPastedGene] = useState<string>("");
  const [pastedSeq, setPastedSeq] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function togglePicked(variantId: string) {
    setPicked((cur) =>
      cur.some((p) => p.catalog_id === variantId)
        ? cur.filter((p) => p.catalog_id !== variantId)
        : [...cur, { catalog_id: variantId, zygosity: "heterozygous" }],
    );
  }

  function setZygosity(variantId: string, z: Zygosity) {
    setPicked((cur) =>
      cur.map((p) => (p.catalog_id === variantId ? { ...p, zygosity: z } : p)),
    );
  }

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const variants: VariantInput[] = picked.map((p) => ({
        catalog_id: p.catalog_id,
        zygosity: p.zygosity,
      }));
      if (pastedSeq.trim()) {
        variants.push({
          gene_symbol: pastedGene || null,
          protein_sequence: pastedSeq.trim(),
          zygosity: "heterozygous",
        });
      }
      if (variants.length === 0 && !allowEmptyVariants) {
        throw new Error(
          "pick at least one variant, paste a sequence, or upload a CT scan",
        );
      }
      const result = await api.analyze({ drug_id: drugId, variants });
      onResult(result, { drugId, variants });
    } catch (err) {
      setError(err instanceof Error ? err.message : "analysis failed");
    } finally {
      setSubmitting(false);
    }
  }

  return {
    catalog,
    isLoading,
    drugId,
    setDrugId,
    picked,
    togglePicked,
    setZygosity,
    pastedGene,
    setPastedGene,
    pastedSeq,
    setPastedSeq,
    submitting,
    error,
    submit,
  };
}

/** Step 1 body: medication dropdown with a collapsible "medical details" pane. */
export function DrugPickerSection({ form }: { form: BCAnalysisFormHandle }) {
  if (form.isLoading || !form.catalog) {
    return <div className="text-sm text-gray-500">Loading medications…</div>;
  }
  const drug = form.catalog.drugs.find((d) => d.id === form.drugId);
  return (
    <div className="space-y-3">
      <select
        className="w-full border rounded-lg px-3 py-2.5 text-sm bg-white"
        value={form.drugId}
        onChange={(e) => form.setDrugId(e.target.value)}
      >
        {form.catalog.drugs.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name} ({drugAudience(d.category)})
          </option>
        ))}
      </select>
      {drug ? (
        <details>
          <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground inline-block">
            What is {drug.name}?
          </summary>
          <div className="mt-2 p-4 bg-slate-50 rounded-lg text-sm text-gray-700 space-y-3 border leading-relaxed">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-0.5">
                Used for
              </div>
              <div>{drug.indication}</div>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-0.5">
                How it works
              </div>
              <div>{drug.mechanism}</div>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-0.5">
                Main target
              </div>
              <div>
                {drug.primary_target_gene}
                {drug.metabolizing_gene ? (
                  <span className="text-muted-foreground">
                    {" · processed by "}
                    {drug.metabolizing_gene}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        </details>
      ) : null}
    </div>
  );
}

/** Step 3 body: grouped variant checklist + raw-protein-sequence advanced box. */
export function VariantPickerSection({ form }: { form: BCAnalysisFormHandle }) {
  const catalog = form.catalog;
  const geneBySymbol = useMemo(() => {
    const m = new Map<string, Catalog["genes"][number]>();
    catalog?.genes.forEach((g) => m.set(g.symbol, g));
    return m;
  }, [catalog]);
  const variantsByEffect = useMemo(() => {
    const groups: Record<string, Map<string, CatalogVariant[]>> = {};
    catalog?.variants.forEach((v) => {
      const bucket = (groups[v.effect_type] ??= new Map());
      const list = bucket.get(v.gene_symbol) ?? [];
      list.push(v);
      bucket.set(v.gene_symbol, list);
    });
    return groups;
  }, [catalog]);

  if (form.isLoading || !catalog) {
    return <div className="text-sm text-gray-500">Loading variant catalog…</div>;
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        Variants are grouped by what they affect. Hover the{" "}
        <HelpCircle
          className="w-3 h-3 inline align-[-2px] text-gray-400"
          aria-hidden
        />{" "}
        icon next to any gene for a plain-English explanation. Skip this step if
        you don&apos;t know your variants.
      </p>
      <div className="space-y-4 max-h-[420px] overflow-y-auto border rounded p-3 bg-white">
        {EFFECT_GROUP_ORDER.map((effectType) => {
          const bucket = variantsByEffect[effectType];
          if (!bucket || bucket.size === 0) return null;
          return (
            <div key={effectType} className="space-y-2">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-primary">
                  {EFFECT_LABELS[effectType].title}
                </div>
                <div className="text-[11px] text-gray-500">
                  {EFFECT_LABELS[effectType].blurb}
                </div>
              </div>
              {Array.from(bucket.entries()).map(([geneSym, vars]) => {
                const gene = geneBySymbol.get(geneSym);
                return (
                  <div key={geneSym} className="pl-2 border-l-2 border-slate-200">
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xs font-semibold font-mono">
                        {geneSym}
                      </span>
                      <span className="text-[11px] text-gray-500">
                        {gene?.name}
                      </span>
                      {gene?.plain_role ? (
                        <GeneTooltip blurb={gene.plain_role} />
                      ) : null}
                    </div>
                    <ul className="mt-1 space-y-1">
                      {vars.map((v) => {
                        const selected = form.picked.find(
                          (p) => p.catalog_id === v.id,
                        );
                        return (
                          <li key={v.id} className="flex items-start gap-2">
                            <input
                              type="checkbox"
                              className="mt-1"
                              checked={!!selected}
                              onChange={() => form.togglePicked(v.id)}
                              id={`var-${v.id}`}
                            />
                            <label
                              htmlFor={`var-${v.id}`}
                              className="text-xs flex-1 cursor-pointer"
                            >
                              <div className="flex items-baseline gap-1.5 flex-wrap">
                                <span className="font-mono">{v.name}</span>
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[10px] ${sigColor(v.clinical_significance)}`}
                                >
                                  {sigLabel(v.clinical_significance)}
                                </span>
                              </div>
                              <div className="text-gray-700 mt-0.5">
                                {v.plain_summary}
                              </div>
                            </label>
                            {selected ? (
                              <select
                                value={selected.zygosity}
                                onChange={(e) =>
                                  form.setZygosity(v.id, e.target.value as Zygosity)
                                }
                                className="text-xs border rounded px-1.5 py-0.5 bg-white"
                                title="Heterozygous = one copy; homozygous = both copies"
                              >
                                <option value="heterozygous">1 copy</option>
                                <option value="homozygous">2 copies</option>
                              </select>
                            ) : null}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>

      <details className="group">
        <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5">
          Advanced: I have a raw protein sequence
        </summary>
        <div className="mt-3 p-4 rounded-lg border bg-slate-50 space-y-2">
          <p className="text-xs text-gray-600">
            Paste a protein sequence (single-letter amino-acid code). We&apos;ll
            auto-detect which of the supported genes it belongs to and flag any
            differences from the reference.
          </p>
          <div className="flex gap-2 flex-wrap">
            <select
              value={form.pastedGene}
              onChange={(e) => form.setPastedGene(e.target.value)}
              className="text-sm border rounded px-2 py-1 bg-white"
            >
              <option value="">auto-detect</option>
              {catalog.genes.map((g) => (
                <option key={g.symbol} value={g.symbol}>
                  {g.symbol}
                </option>
              ))}
            </select>
            <textarea
              value={form.pastedSeq}
              onChange={(e) => form.setPastedSeq(e.target.value)}
              placeholder="MAQIGH..."
              rows={3}
              className="flex-1 text-xs font-mono border rounded p-2 min-w-[300px] bg-white"
            />
          </div>
        </div>
      </details>
    </div>
  );
}

/** Submit button + any error — rendered at the end of Step 3. */
export function RunAnalysisButton({ form }: { form: BCAnalysisFormHandle }) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <button
        type="button"
        onClick={() => {
          void form.submit();
        }}
        disabled={form.submitting}
        className="px-6 py-3 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
      >
        {form.submitting ? "Analyzing…" : "Show me how this affects me"}
      </button>
      {form.error ? (
        <span className="text-sm text-red-600">{form.error}</span>
      ) : null}
    </div>
  );
}

function GeneTooltip({ blurb }: { blurb: string }) {
  return (
    <span className="group relative inline-flex">
      <HelpCircle
        className="w-3.5 h-3.5 text-gray-400 hover:text-gray-700 cursor-help"
        aria-hidden
      />
      <span
        role="tooltip"
        className="invisible group-hover:visible absolute left-5 top-0 z-20 w-72 bg-white border rounded-lg p-3 text-[11px] leading-relaxed shadow-lg text-gray-800"
      >
        {blurb}
      </span>
    </span>
  );
}

function drugAudience(category: string): string {
  switch (category) {
    case "hormone_therapy":
      return "hormone-sensitive breast cancer";
    case "her2_targeted":
      return "HER2-positive breast cancer / CML";
    case "cdk46_inhibitor":
      return "HR+ breast cancer (cell cycle)";
    case "parp_inhibitor":
      return "BRCA-mutated breast/ovarian cancer";
    case "pi3k_inhibitor":
      return "PIK3CA-mutated breast cancer";
    case "aromatase_inhibitor":
      return "postmenopausal breast cancer";
    case "chemotherapy":
      return "breast / colorectal / leukemia chemotherapy";
    default:
      return category.replace(/_/g, " ");
  }
}

function sigColor(s: string): string {
  switch (s) {
    case "pathogenic":
    case "likely_pathogenic":
      return "bg-red-100 text-red-800";
    case "drug_response":
      return "bg-amber-100 text-amber-800";
    case "benign":
    case "likely_benign":
      return "bg-green-100 text-green-800";
    default:
      return "bg-gray-100 text-gray-700";
  }
}

function sigLabel(s: string): string {
  switch (s) {
    case "pathogenic":
      return "causes disease";
    case "likely_pathogenic":
      return "likely causes disease";
    case "uncertain":
      return "uncertain";
    case "likely_benign":
      return "likely harmless";
    case "benign":
      return "harmless";
    case "drug_response":
      return "affects drugs";
    default:
      return s.replace(/_/g, " ");
  }
}
