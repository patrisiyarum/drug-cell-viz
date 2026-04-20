"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  AnalysisResult,
  Catalog,
  CatalogVariant,
  VariantInput,
  Zygosity,
} from "@/lib/bc-types";

interface SelectedVariant {
  catalog_id: string;
  zygosity: Zygosity;
}

interface Props {
  onResult: (result: AnalysisResult) => void;
}

export function BCAnalysisForm({ onResult }: Props) {
  const { data: catalog, isLoading } = useQuery<Catalog>({
    queryKey: ["bc-catalog"],
    queryFn: () => api.getCatalog(),
  });

  const [drugId, setDrugId] = useState<string>("tamoxifen");
  const [picked, setPicked] = useState<SelectedVariant[]>([
    { catalog_id: "CYP2D6_star4", zygosity: "homozygous" },
  ]);
  const [pastedGene, setPastedGene] = useState<string>("");
  const [pastedSeq, setPastedSeq] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      if (pastedGene && pastedSeq.trim()) {
        variants.push({
          gene_symbol: pastedGene,
          protein_sequence: pastedSeq.trim(),
          zygosity: "heterozygous",
        });
      }
      if (variants.length === 0) {
        throw new Error("pick at least one variant from the catalog or paste a sequence");
      }
      const result = await api.analyze({ drug_id: drugId, variants });
      onResult(result);
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
        <label className="block text-sm font-medium mb-1">1. Choose a breast cancer drug</label>
        <select
          className="w-full md:w-auto border rounded px-3 py-2 text-sm"
          value={drugId}
          onChange={(e) => setDrugId(e.target.value)}
        >
          {catalog.drugs.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} · {d.category.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        {drug ? (
          <div className="mt-2 p-3 bg-slate-100 rounded text-xs text-gray-700 space-y-1">
            <div>
              <span className="font-medium">Mechanism:</span> {drug.mechanism}
            </div>
            <div>
              <span className="font-medium">Primary target:</span> {drug.primary_target_gene}
              {drug.metabolizing_gene ? (
                <>
                  {" · "}
                  <span className="font-medium">Metabolized by:</span> {drug.metabolizing_gene}
                </>
              ) : null}
            </div>
            <div>
              <span className="font-medium">Indication:</span> {drug.indication}
            </div>
          </div>
        ) : null}
      </section>

      <section>
        <label className="block text-sm font-medium mb-1">
          2. Your variants (pick from catalog)
        </label>
        <p className="text-xs text-gray-500 mb-2">
          Select one or more curated variants. Zygosity affects PGx verdicts.
        </p>
        <div className="space-y-3 max-h-[320px] overflow-y-auto border rounded p-3 bg-white">
          {Array.from(variantsByGene.entries()).map(([gene, vars]) => (
            <div key={gene}>
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                {gene}
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
                      <label htmlFor={`var-${v.id}`} className="text-xs flex-1 cursor-pointer">
                        <span className="font-mono">{v.name}</span>
                        <span
                          className={`ml-2 px-1.5 py-0.5 rounded text-[10px] ${sigColor(v.clinical_significance)}`}
                        >
                          {v.clinical_significance.replace(/_/g, " ")}
                        </span>
                        <div className="text-gray-600 mt-0.5">{v.effect_summary}</div>
                      </label>
                      {selected ? (
                        <select
                          value={selected.zygosity}
                          onChange={(e) => setZygosity(v.id, e.target.value as Zygosity)}
                          className="text-xs border rounded px-1 py-0.5"
                        >
                          <option value="heterozygous">het</option>
                          <option value="homozygous">hom</option>
                        </select>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section>
        <label className="block text-sm font-medium mb-1">
          3. Or paste your protein sequence (optional)
        </label>
        <p className="text-xs text-gray-500 mb-2">
          For a supported gene, paste the full or partial protein sequence. We'll align it to the
          wild type and infer residue differences.
        </p>
        <div className="flex gap-2 flex-wrap">
          <select
            value={pastedGene}
            onChange={(e) => setPastedGene(e.target.value)}
            className="text-sm border rounded px-2 py-1"
          >
            <option value="">— none —</option>
            {catalog.genes.map((g) => (
              <option key={g.symbol} value={g.symbol}>
                {g.symbol}
              </option>
            ))}
          </select>
          <textarea
            value={pastedSeq}
            onChange={(e) => setPastedSeq(e.target.value)}
            placeholder="MAQIGH... (single-letter amino acid sequence)"
            rows={3}
            className="flex-1 text-xs font-mono border rounded p-2 min-w-[300px]"
          />
        </div>
      </section>

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="px-4 py-2 rounded bg-black text-white disabled:opacity-50"
        >
          {submitting ? "Analyzing…" : "Analyze drug × variants"}
        </button>
        {error ? <span className="text-sm text-red-600">{error}</span> : null}
      </div>
    </form>
  );
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
