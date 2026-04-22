"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/lib/api";
import type { AnalysisResult, Demos, DemoPatient, VariantInput } from "@/lib/bc-types";

interface Props {
  onResult: (result: AnalysisResult, patient: DemoPatient) => void;
}

export function DemoPatientPicker({ onResult }: Props) {
  const { data, isLoading } = useQuery<Demos>({
    queryKey: ["bc-demos"],
    queryFn: () => api.getDemos(),
  });
  const [runningId, setRunningId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (isLoading || !data) {
    return <div className="text-sm text-gray-500">Loading demo patients…</div>;
  }

  async function runDemo(p: DemoPatient) {
    setRunningId(p.id);
    setError(null);
    try {
      const variants: VariantInput[] = p.variant_ids.map((vid) => ({
        catalog_id: vid,
        zygosity: p.zygosity_overrides[vid] ?? "heterozygous",
      }));
      const result = await api.analyze({ drug_id: p.drug_id, variants });
      onResult(result, p);
    } catch (err) {
      setError(err instanceof Error ? err.message : "demo failed");
    } finally {
      setRunningId(null);
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex items-start gap-2">
        <div className="flex-1">
          <h2 className="font-semibold text-sm">Two-minute demo walkthrough</h2>
          <p className="text-xs text-gray-600">
            Three preset patients covering the green-light case, a well-studied caution
            case, and a life-threatening toxicity case.
          </p>
        </div>
      </div>

      <div className="text-[11px] italic text-gray-600 bg-slate-100 rounded px-2 py-1 inline-block">
        {data.note}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {data.patients.map((p) => (
          <article
            key={p.id}
            className="border rounded bg-white p-3 flex flex-col justify-between"
          >
            <div className="space-y-2">
              <div className="flex items-baseline justify-between gap-2">
                <h3 className="font-semibold text-sm">{p.name}</h3>
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${patientAccent(p.id)}`}>
                  {p.indication}
                </span>
              </div>
              <div className="text-xs font-medium text-gray-700">{p.scenario}</div>
              <div className="text-xs text-gray-600">{p.narrative}</div>
              <div className="text-[11px] bg-slate-50 rounded border px-2 py-1 font-mono space-y-0.5">
                <div className="text-gray-500 not-italic">
                  drug: <span className="text-gray-900">{p.drug_id}</span>
                </div>
                {Object.entries(p.genotype_summary).map(([gene, geno]) => (
                  <div key={gene} className="text-gray-700">
                    {gene}: <span className="text-gray-900">{geno}</span>
                  </div>
                ))}
              </div>
            </div>
            <button
              onClick={() => runDemo(p)}
              disabled={runningId === p.id}
              className="mt-3 w-full px-3 py-1.5 rounded bg-black text-white text-xs disabled:opacity-50"
            >
              {runningId === p.id ? "Running…" : `Run ${p.name}`}
            </button>
          </article>
        ))}
      </div>

      {error ? <div className="text-sm text-red-600">{error}</div> : null}
    </section>
  );
}

function patientAccent(id: string): string {
  switch (id) {
    case "patient_a":
      return "bg-green-100 text-green-800";
    case "patient_b":
      return "bg-amber-100 text-amber-800";
    case "patient_c":
      return "bg-red-100 text-red-800";
    default:
      return "bg-slate-100 text-slate-700";
  }
}
