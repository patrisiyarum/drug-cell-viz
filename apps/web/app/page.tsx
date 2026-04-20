"use client";

import { useState } from "react";

import { AnalysisResultPanel } from "@/components/AnalysisResultPanel";
import { BCAnalysisForm } from "@/components/BCAnalysisForm";
import type { AnalysisResult } from "@/lib/bc-types";

export default function HomePage() {
  const [result, setResult] = useState<AnalysisResult | null>(null);

  return (
    <main className="min-h-screen flex flex-col bg-slate-50">
      <div className="flex-1 p-6 md:p-8 space-y-6 max-w-7xl mx-auto w-full">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold">Breast cancer drug × your variants</h1>
          <p className="text-sm text-gray-600">
            Pick a breast cancer drug, pick (or paste) your variants, and see how they interact:
            curated CPIC / FDA pharmacogenomic guidance plus a 3D view of the drug on its target
            with your variant residues highlighted.
          </p>
        </header>

        <div className="bg-white rounded border p-5">
          <BCAnalysisForm onResult={setResult} />
        </div>

        {result ? <AnalysisResultPanel result={result} /> : null}
      </div>

      <footer className="border-t p-4 text-xs text-gray-700 bg-red-50">
        <strong>Educational use only.</strong> This tool is not a medical device and does not
        provide treatment recommendations. It summarizes public pharmacogenomic evidence (CPIC,
        FDA labeling) alongside a structural heuristic. Do not use for clinical decision-making.
        Consult a qualified oncologist and a clinical pharmacogenomicist — genetic testing must
        be performed by a CLIA-certified laboratory.
      </footer>
    </main>
  );
}
