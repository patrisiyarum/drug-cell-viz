"use client";

import { useState } from "react";
import { FileText } from "lucide-react";

import { api } from "@/lib/api";
import type { AnalysisResult } from "@/lib/bc-types";

interface Props {
  result: AnalysisResult;
  patientLabel?: string | null;
}

/**
 * One-click PDF download of the doctor-visit report.
 *
 * Rendered as a card that matches the HrdCard / CurrentDrugAssessmentCard
 * visual rhythm (rounded-2xl border, p-5 md:p-6) so it sits cleanly within
 * the right column's stack instead of as a bare floating button.
 *
 * The server renders a reportlab PDF on demand; we Blob + object-URL it so
 * we don't have to store the PDF anywhere. The filename mirrors the server
 * Content-Disposition default.
 */
export function DoctorVisitPdfButton({ result, patientLabel }: Props) {
  const [downloading, setDownloading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onClick() {
    setDownloading(true);
    setErr(null);
    try {
      const blob = await api.downloadReportPdf(result, patientLabel);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pharmacogenomic-report-${result.drug_id}-${result.id.slice(
        0,
        8,
      )}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not generate PDF");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section className="bg-card border rounded-2xl p-5 md:p-6 flex items-center gap-4 flex-wrap">
      <FileText className="w-5 h-5 text-primary flex-shrink-0" aria-hidden />
      <div className="flex-1 min-w-[200px]">
        <div className="text-base font-semibold">
          Download your report
        </div>
        {err ? <div className="text-xs text-red-600 mt-1">{err}</div> : null}
      </div>
      <button
        type="button"
        onClick={onClick}
        disabled={downloading}
        className="inline-flex items-center justify-center rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-60 transition-opacity"
      >
        {downloading ? "Generating…" : "Download PDF"}
      </button>
    </section>
  );
}
