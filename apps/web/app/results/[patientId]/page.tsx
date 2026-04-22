"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { ResultsReport } from "@/components/ResultsReport";
import { api } from "@/lib/api";
import type { AnalysisResult, DemoPatient, Demos } from "@/lib/bc-types";

export default function ResultsViewPage() {
  const params = useParams<{ patientId: string }>();
  const patientId = params?.patientId;

  const { data: demos } = useQuery<Demos>({
    queryKey: ["bc-demos"],
    queryFn: () => api.getDemos(),
  });

  const patient = useMemo(
    () => demos?.patients.find((p) => p.id === patientId) ?? null,
    [demos, patientId],
  );

  const analysis = useQuery<AnalysisResult>({
    queryKey: ["analysis", patientId, patient?.drug_id],
    enabled: !!patient,
    queryFn: () =>
      api.analyze({
        drug_id: patient!.drug_id,
        variants: patient!.variant_ids.map((vid) => ({
          catalog_id: vid,
          zygosity: patient!.zygosity_overrides[vid] ?? "heterozygous",
        })),
      }),
  });

  if (!demos) return <CenteredMessage>Loading case.</CenteredMessage>;
  if (!patient) {
    return (
      <CenteredMessage>
        <p className="text-2xl font-semibold mb-3">Case not found</p>
        <Link href="/demo" className="text-primary hover:underline">
          Back to cases
        </Link>
      </CenteredMessage>
    );
  }
  if (analysis.isError) {
    return (
      <CenteredMessage>
        <p className="text-lg font-medium mb-2">Couldn't run the analysis.</p>
        <p className="text-sm text-muted-foreground">{(analysis.error as Error).message}</p>
      </CenteredMessage>
    );
  }
  if (!analysis.data) return <CenteredMessage>Analyzing {patient.name}.</CenteredMessage>;

  return (
    <div className="flex flex-col bg-white">
      <ResultsHeader patient={patient} />
      <main className="flex-1">
        <div className="max-w-[1600px] mx-auto px-6 md:px-8 py-8">
          <div className="hidden print-header">
            <h1 className="text-3xl mb-2 font-semibold">
              {patient.persona_name}'s Pharmacogenomics Report
            </h1>
            <p className="text-lg">
              {patient.persona_name}, {patient.age}. {patient.medication_display} for{" "}
              {patient.indication}.
            </p>
            <hr className="my-6" />
          </div>
          <ResultsReport result={analysis.data} patient={patient} />
        </div>
      </main>
    </div>
  );
}

function ResultsHeader({ patient }: { patient: DemoPatient }) {
  return (
    <header className="border-b bg-card no-print">
      <div className="max-w-[1600px] mx-auto px-6 md:px-8 py-5 flex items-center justify-between gap-4 flex-wrap">
        <Link
          href="/demo"
          className="text-muted-foreground hover:text-foreground transition-colors text-sm"
        >
          ← Back to cases
        </Link>
        <div className="text-right">
          <p className="text-sm text-muted-foreground">
            {patient.persona_name}, {patient.age}. Starting {patient.medication_display} for{" "}
            {patient.indication}.
          </p>
        </div>
      </div>
    </header>
  );
}

function CenteredMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-[70vh] flex items-center justify-center bg-white px-6">
      <div className="text-center max-w-md">{children}</div>
    </div>
  );
}
