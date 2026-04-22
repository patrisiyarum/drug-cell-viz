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

interface SelectedVariant {
  catalog_id: string;
  zygosity: Zygosity;
}

interface Props {
  // The /build page uses the second and third args to remember what was
  // submitted so the "try this drug instead" button on the relevance-warning
  // banner can re-run with the same variants.
  onResult: (
    result: AnalysisResult,
    context: { drugId: string; variants: VariantInput[] },
  ) => void;
  // When /build wants to programmatically switch drugs (from the warning
  // banner), it passes the new drugId here and we sync the internal picker.
  drugIdOverride?: string;
  // Variants that a pre-step (23andMe upload) already detected. We merge these
  // into the picker state so the user sees them pre-selected and can still
  // uncheck or add more.
  presetVariants?: SelectedVariant[];
}

export function BCAnalysisForm({
  onResult,
  drugIdOverride,
  presetVariants,
}: Props) {
  const { data: catalog, isLoading } = useQuery<Catalog>({
    queryKey: ["bc-catalog"],
    queryFn: () => api.getCatalog(),
  });

  const [drugId, setDrugId] = useState<string>(drugIdOverride ?? "tamoxifen");

  // Keep the internal picker in sync when /build asks to switch drugs.
  useEffect(() => {
    if (drugIdOverride && drugIdOverride !== drugId) setDrugId(drugIdOverride);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drugIdOverride]);
  const [picked, setPicked] = useState<SelectedVariant[]>([
    { catalog_id: "CYP2D6_star4", zygosity: "homozygous" },
  ]);

  // Merge any upload-detected variants into the picker (without clobbering
  // manual selections). Runs whenever presetVariants changes — i.e. after a
  // new 23andMe file is parsed.
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

  const geneBySymbol = useMemo(() => {
    const m = new Map<string, Catalog["genes"][number]>();
    catalog?.genes.forEach((g) => m.set(g.symbol, g));
    return m;
  }, [catalog]);

  // Group variants by effect_type → gene, so the picker reads like
  // "Drug-metabolism genes > CYP2D6 > (variants)" instead of a raw gene list.
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

  const variantsByGene = useMemo(() => {
    const m = new Map<string, CatalogVariant[]>();
    catalog?.variants.forEach((v) => {
      const list = m.get(v.gene_symbol) ?? [];
      list.push(v);
      m.set(v.gene_symbol, list);
    });
    return m;
  }, [catalog]);

  if (isLoading || !catalog) {
    return <div className="text-sm text-gray-500">Loading breast cancer catalog…</div>;
  }

  const drug = catalog.drugs.find((d) => d.id === drugId);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const variants: VariantInput[] = picked.map((p) => ({
        catalog_id: p.catalog_id,
        zygosity: p.zygosity,
      }));
      if (pastedSeq.trim()) {
        // Gene is optional. If left as "none", the server auto-detects which
        // gene the pasted sequence belongs to by comparing against UniProt.
        variants.push({
          gene_symbol: pastedGene || null,
          protein_sequence: pastedSeq.trim(),
          zygosity: "heterozygous",
        });
      }
      if (variants.length === 0) {
        throw new Error("pick at least one variant from the catalog or paste a sequence");
      }
      const result = await api.analyze({ drug_id: drugId, variants });
      onResult(result, { drugId, variants });
    } catch (err) {
      setError(err instanceof Error ? err.message : "analysis failed");
    } finally {
      setSubmitting(false);
    }
  }

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

  return (
    <form onSubmit={onSubmit} className="space-y-5">
      <section>
        <StepLabel n={1} title="What medication is your doctor considering?" />
        <select
          className="w-full md:w-auto border rounded-lg px-3 py-2.5 text-sm bg-white"
          value={drugId}
          onChange={(e) => setDrugId(e.target.value)}
        >
          {catalog.drugs.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} — {drugAudience(d.category)}
            </option>
          ))}
        </select>
        {drug ? (
          <details className="mt-3">
            <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground inline-block">
              What is {drug.name}? (medical details)
            </summary>
            <div className="mt-2 p-3 bg-slate-50 rounded-lg text-xs text-gray-700 space-y-1.5 border">
              <div>
                <span className="font-medium">Used for:</span> {drug.indication}
              </div>
              <div>
                <span className="font-medium">How it works:</span> {drug.mechanism}
              </div>
              <div>
                <span className="font-medium">Main target:</span> {drug.primary_target_gene}
                {drug.metabolizing_gene ? (
                  <>
                    {" · "}
                    <span className="font-medium">Processed by:</span> {drug.metabolizing_gene}
                  </>
                ) : null}
              </div>
            </div>
          </details>
        ) : null}
      </section>

      <section>
        <StepLabel
          n={2}
          title="Do you have any of these genetic variants?"
          hint="If you don't know, skip this step. Or try the 23andMe upload (coming soon) or the preset patient cases."
        />
        <p className="text-xs text-gray-500 mb-3">
          Variants are grouped by what they affect. Hover the{" "}
          <HelpCircle className="w-3 h-3 inline align-[-2px] text-gray-400" aria-hidden />{" "}
          icon next to any gene for a plain-English explanation.
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
                        <span className="text-xs font-semibold font-mono">{geneSym}</span>
                        <span className="text-[11px] text-gray-500">
                          {gene?.name}
                        </span>
                        {gene?.plain_role ? (
                          <GeneTooltip blurb={gene.plain_role} />
                        ) : null}
                      </div>
                      <ul className="mt-1 space-y-1">
                        {vars.map((v) => {
                          const selected = picked.find((p) => p.catalog_id === v.id);
                          return (
                            <li key={v.id} className="flex items-start gap-2">
                              <input
                                type="checkbox"
                                className="mt-1"
                                checked={!!selected}
                                onChange={() => togglePicked(v.id)}
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
                                    setZygosity(v.id, e.target.value as Zygosity)
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
      </section>

      <details className="group">
        <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5">
          Advanced: I have a raw protein sequence
          <span className="text-xs text-gray-400 group-open:hidden">(click to expand)</span>
        </summary>
        <div className="mt-3 p-4 rounded-lg border bg-slate-50 space-y-2">
          <p className="text-xs text-gray-600">
            Paste a protein sequence (single-letter amino-acid code). We'll
            auto-detect which of the supported genes it belongs to and flag any
            differences from the reference. You almost never need this unless
            you're working from a clinical report.
          </p>
          <div className="flex gap-2 flex-wrap">
            <select
              value={pastedGene}
              onChange={(e) => setPastedGene(e.target.value)}
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
              value={pastedSeq}
              onChange={(e) => setPastedSeq(e.target.value)}
              placeholder="MAQIGH..."
              rows={3}
              className="flex-1 text-xs font-mono border rounded p-2 min-w-[300px] bg-white"
            />
          </div>
        </div>
      </details>

      <div className="pt-2 border-t flex items-center gap-3 flex-wrap">
        <button
          type="submit"
          disabled={submitting}
          className="px-6 py-3 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {submitting ? "Analyzing…" : "Show me how this affects me"}
        </button>
        {error ? <span className="text-sm text-red-600">{error}</span> : null}
      </div>
    </form>
  );
}

function StepLabel({
  n,
  title,
  hint,
}: {
  n: number;
  title: string;
  hint?: string;
}) {
  return (
    <div className="mb-2">
      <div className="flex items-center gap-2">
        <span className="w-6 h-6 rounded-full bg-primary text-primary-foreground text-xs font-semibold flex items-center justify-center">
          {n}
        </span>
        <label className="font-medium">{title}</label>
      </div>
      {hint ? <p className="text-xs text-gray-500 ml-8 mt-0.5">{hint}</p> : null}
    </div>
  );
}

function drugAudience(category: string): string {
  // Turn the enum-style categories into plain-English "used for" blurbs so
  // the dropdown reads as "Tamoxifen — hormone-sensitive breast cancer"
  // instead of "Tamoxifen · hormone_therapy".
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
  // Plain-English labels for the clinical_significance pill. The raw values
  // (pathogenic, drug_response) are technical; patients will read "causes
  // disease" and "changes drug response" instead.
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
