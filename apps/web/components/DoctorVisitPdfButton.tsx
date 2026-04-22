"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { AnalysisResult } from "@/lib/bc-types";

interface Props {
  result: AnalysisResult;
  patientLabel?: string | null;
}

/**
 * One-click PDF download of the doctor-visit report.
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
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={onClick}
        disabled={downloading}
        className="inline-flex items-center gap-2 rounded-xl border-2 border-primary px-5 py-2.5 text-sm font-medium text-primary hover:bg-primary hover:text-primary-foreground disabled:opacity-60 transition-colors"
      >
        <span aria-hidden>📄</span>
        {downloading ? "Generating PDF…" : "Download report for my doctor visit"}
      </button>
      {err ? <span className="text-xs text-red-600">{err}</span> : null}
    </div>
  );
}
