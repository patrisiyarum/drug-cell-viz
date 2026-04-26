"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  FileCheck2,
  Pill,
  Sparkles,
} from "lucide-react";

import { ResultsReport } from "@/components/ResultsReport";
import { api } from "@/lib/api";
import type {
  AnalysisResult,
  Catalog,
  DemoPatient,
  Demos,
} from "@/lib/bc-types";

/**
 * Guided walkthrough for preset demo patients. Pre-fills every step of the
 * /build flow so the user sees what the app does at each stage — the drug
 * picker pre-selects the case's drug, the upload card shows a fake
 * "uploaded" fixture VCF with parsed detections, the variant picker shows
 * the catalog entries highlighted, and the final report renders below.
 *
 * This page doesn't do any real file upload — everything the patient needs
 * is already in the preset. The goal is to *demonstrate* the flow, not
 * to let the user interact with each step.
 */
export default function WalkthroughPage() {
  const params = useParams<{ patientId: string }>();
  const patientId = params?.patientId;

  const { data: demos } = useQuery<Demos>({
    queryKey: ["bc-demos"],
    queryFn: () => api.getDemos(),
  });
  const { data: catalog } = useQuery<Catalog>({
    queryKey: ["bc-catalog"],
    queryFn: () => api.getCatalog(),
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

  const reportRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (analysis.data && reportRef.current) {
      // Soft scroll so the user naturally ends on the finished report after
      // the walkthrough loads.
      reportRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [analysis.data?.id]);

  if (!demos || !catalog) {
    return <CenteredMessage>Loading the walkthrough.</CenteredMessage>;
  }
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

  const drug = catalog.drugs.find((d) => d.id === patient.drug_id);
  const variants = patient.variant_ids
    .map((vid) => catalog.variants.find((v) => v.id === vid))
    .filter((v): v is NonNullable<typeof v> => !!v);

  // Map a catalog variant id to the fixture VCF path we ship in the repo,
  // where possible. The fixture is what the walkthrough's Step 2 shows as
  // "uploaded"; if there's no matching fixture we fall back to a short
  // "catalog-only" explanation in that step.
  const fixtureFor = FIXTURES[patientId ?? ""];

  return (
    <div className="flex flex-col bg-white min-h-screen">
      <header className="border-b bg-card no-print">
        <div className="max-w-[1600px] mx-auto px-6 md:px-8 py-5 flex items-center justify-between gap-4 flex-wrap">
          <Link
            href="/demo"
            className="text-muted-foreground hover:text-foreground transition-colors text-sm"
          >
            ← Back to cases
          </Link>
          <div className="text-right text-sm">
            <span className="text-muted-foreground">
              Walking through {patient.persona_name}
              &apos;s story
            </span>
          </div>
        </div>
      </header>

      <main className="flex-1 px-6 md:px-8 py-10">
        <div className="max-w-3xl mx-auto space-y-6">
          <div className="space-y-2">
            <h1 className="text-3xl md:text-4xl font-semibold">
              {patient.persona_name}&apos;s walkthrough
            </h1>
            <p className="text-muted-foreground text-base leading-relaxed">
              {patient.persona_name}, {patient.age}. Starting{" "}
              {patient.medication_display} for {patient.indication}. Below is
              every step the app would take with this data already supplied.
            </p>
          </div>

          {/* ---- STEP 1: drug pre-filled ---- */}
          <StepCard
            n={1}
            title="Pick a medication"
            subtitle="Pre-filled for this case."
            icon={<Pill className="w-4 h-4" aria-hidden />}
          >
            <div className="flex items-baseline gap-2 flex-wrap text-sm">
              <span className="text-muted-foreground">Selected:</span>
              <span className="font-semibold text-base">
                {drug?.name ?? patient.drug_id}
              </span>
              {drug ? (
                <span className="text-xs text-muted-foreground">
                  ({drug.category.replace(/_/g, " ")})
                </span>
              ) : null}
            </div>
          </StepCard>

          {/* ---- STEP 2: fixture file "uploaded" ---- */}
          <StepCard
            n={2}
            title="Upload your data"
            subtitle={
              fixtureFor
                ? `Fixture ${fixtureFor.path} loaded for this walkthrough.`
                : `Variants for ${patient.persona_name} were selected directly from the curated catalog (no file upload needed).`
            }
            icon={<FileCheck2 className="w-4 h-4" aria-hidden />}
          >
            {fixtureFor ? (
              <div className="space-y-3">
                <div className="flex items-start gap-2 text-sm">
                  <CheckCircle2
                    className="w-4 h-4 text-success flex-shrink-0 mt-0.5"
                    aria-hidden
                  />
                  <div className="flex-1">
                    <span className="font-medium">File read.</span>{" "}
                    <span className="text-muted-foreground">
                      {fixtureFor.records} record
                      {fixtureFor.records === 1 ? "" : "s"} scanned; matched{" "}
                      {variants.length} catalog variant
                      {variants.length === 1 ? "" : "s"}.
                    </span>
                  </div>
                </div>
                <ul className="space-y-1">
                  {variants.map((v) => (
                    <li
                      key={v.id}
                      className="text-xs border rounded-lg p-2 bg-white"
                    >
                      <span className="font-mono">{v.name}</span>{" "}
                      <span className="text-muted-foreground">
                        · {v.gene_symbol} ·{" "}
                        {(patient.zygosity_overrides[v.id] ?? "heterozygous") ===
                        "homozygous"
                          ? "both copies"
                          : "one copy"}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-muted-foreground">
                  You can also upload your own clinical VCF on{" "}
                  <Link href="/build" className="text-primary hover:underline">
                    /build
                  </Link>
                  .
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                For this case the variants come directly from the curated
                catalog. Real users would either upload a clinical VCF on{" "}
                <Link href="/build" className="text-primary hover:underline">
                  /build
                </Link>{" "}
                or pick variants manually in step 3.
              </p>
            )}
          </StepCard>

          {/* ---- STEP 3: variants pre-selected ---- */}
          <StepCard
            n={3}
            title="Select your variants"
            subtitle={`${variants.length} variant${variants.length === 1 ? "" : "s"} selected for ${patient.persona_name}.`}
            icon={<Sparkles className="w-4 h-4" aria-hidden />}
          >
            <ul className="space-y-2">
              {variants.map((v) => (
                <li
                  key={v.id}
                  className="rounded-lg border p-3 bg-white space-y-1"
                >
                  <div className="flex items-baseline gap-2 flex-wrap text-sm">
                    <span className="font-mono">{v.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {v.gene_symbol}
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded ${
                        v.clinical_significance === "pathogenic" ||
                        v.clinical_significance === "likely_pathogenic"
                          ? "bg-red-100 text-red-800"
                          : v.clinical_significance === "drug_response"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {v.clinical_significance.replace(/_/g, " ")}
                    </span>
                    <span className="text-xs text-muted-foreground ml-auto">
                      {(patient.zygosity_overrides[v.id] ?? "heterozygous") ===
                      "homozygous"
                        ? "2 copies"
                        : "1 copy"}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {v.plain_summary}
                  </p>
                </li>
              ))}
            </ul>
          </StepCard>
        </div>

        {/* Full report — no step header; the report cards speak for themselves. */}
        <div
          ref={reportRef}
          className="max-w-[1600px] mx-auto mt-10 scroll-mt-6"
        >
          {analysis.isLoading ? (
            <p className="text-sm text-muted-foreground max-w-3xl mx-auto">
              Running the analysis.
            </p>
          ) : analysis.isError ? (
            <p className="text-sm text-red-600 max-w-3xl mx-auto">
              Couldn&apos;t run the analysis:{" "}
              {(analysis.error as Error).message}
            </p>
          ) : analysis.data ? (
            <ResultsReport result={analysis.data} patient={patient} />
          ) : null}
        </div>
      </main>
    </div>
  );
}

// Map demo patient id → the fixture VCF we ship in fixtures/patients/.
// Maya + Diana's catalog variants have matching coordinates in the VCF
// ingestor's _COORDS table, so a fixture VCF can round-trip through
// /api/vcf/analyze and land the expected detection. Priya's BRCA2 variant
// is a frameshift indel that _COORDS doesn't cover (yet — see
// docs/research-roadmap.md for the follow-up), so her walkthrough uses
// the "catalog-only" branch below and skips Step 2's file demo.
const FIXTURES: Record<string, { path: string; records: number }> = {
  maya: { path: "fixtures/patients/patient_maya_brca1.vcf", records: 1 },
  diana: { path: "fixtures/patients/patient_diana_cyp2d6.vcf", records: 1 },
};

function StepCard({
  n,
  title,
  subtitle,
  icon,
  children,
}: {
  n: number;
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-card border rounded-2xl p-5 md:p-6 space-y-4">
      <div className="flex items-start gap-3">
        <StepNumber n={n} />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-lg md:text-xl font-semibold">{title}</h2>
            {icon ? (
              <span className="text-muted-foreground">{icon}</span>
            ) : null}
          </div>
          {subtitle ? (
            <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
          ) : null}
        </div>
      </div>
      <div>{children}</div>
    </section>
  );
}

function StepNumber({ n }: { n: number }) {
  return (
    <span className="w-7 h-7 flex-shrink-0 rounded-full bg-primary text-primary-foreground text-sm font-semibold flex items-center justify-center">
      {n}
    </span>
  );
}

function CenteredMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-[70vh] flex items-center justify-center bg-white px-6">
      <div className="text-center max-w-md">{children}</div>
    </div>
  );
}
