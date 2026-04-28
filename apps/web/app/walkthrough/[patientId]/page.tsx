"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { ResultsReport } from "@/components/ResultsReport";
import { api, type PatientFullProfile } from "@/lib/api";
import type {
  AnalysisResult,
  Catalog,
  DemoPatient,
  Demos,
} from "@/lib/bc-types";

/**
 * Pull tumor-scar numbers (LOH / LST / NtAI) out of a patient's stored
 * upload summaries so the HrdCard's scar panel can pre-fill + auto-run.
 * Looks for the canonical "LOH N · LST N · NTAI N" string we seed.
 */
function findScarPrefill(
  profile: PatientFullProfile | undefined,
): { loh: number; lst: number; ntai: number } | null {
  if (!profile) return null;
  for (const u of profile.uploads) {
    if (!u.summary_json) continue;
    const m = u.summary_json.match(
      /LOH\s+(\d+)[^\d]+LST\s+(\d+)[^\d]+NTAI\s+(\d+)/i,
    );
    if (m) {
      return { loh: Number(m[1]), lst: Number(m[2]), ntai: Number(m[3]) };
    }
  }
  return null;
}

/**
 * Pick the first upload of each kind so the lab tiles can show which
 * actual file in the patient's profile is driving each experiment.
 * Falls back to undefined when the patient has no upload of that kind.
 */
function recordRefsFor(profile: PatientFullProfile | undefined): {
  vcfFilename?: string | null;
  ctScanFilename?: string | null;
  reportFilename?: string | null;
} {
  if (!profile) return {};
  const vcf =
    profile.uploads.find(
      (u) => u.upload_kind === "vcf" || u.upload_kind === "23andme",
    )?.filename ?? null;
  const ct =
    profile.uploads.find((u) => u.upload_kind === "ct_scan")?.filename ?? null;
  const report =
    profile.uploads.find((u) => u.upload_kind === "report")?.filename ?? null;
  return {
    vcfFilename: vcf,
    ctScanFilename: ct,
    reportFilename: report,
  };
}

/**
 * Clinical analysis page for a preset patient. Renders the full ResultsReport
 * (3D molecular view, HRD card, drug-match assessment, PDF download) for the
 * patient referenced by the URL. Header just lets the user back-navigate to
 * the patient's profile.
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

  // Patient profile (for scar-report parsing). Same key as /patient/<id>
  // so React Query shares the cache.
  const profile = useQuery<PatientFullProfile>({
    queryKey: ["patient", patientId],
    queryFn: () => api.getPatientProfile(patientId!),
    enabled: !!patientId,
  });
  const scarPrefill = findScarPrefill(profile.data);
  const recordRefs = recordRefsFor(profile.data);

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
        <p className="text-2xl font-semibold mb-3">Patient not found</p>
        <Link href="/demo" className="text-primary hover:underline">
          ← All patients
        </Link>
      </CenteredMessage>
    );
  }

  return (
    <div className="flex flex-col bg-white min-h-screen">
      <header className="border-b bg-card no-print">
        <div className="max-w-[1600px] mx-auto px-6 md:px-8 py-5 flex items-center justify-between gap-4 flex-wrap">
          <Link
            href={`/patient/${patientId}`}
            className="text-muted-foreground hover:text-foreground transition-colors text-sm"
          >
            ← Back to {patient.persona_name}&apos;s profile
          </Link>
        </div>
      </header>

      <main className="flex-1 px-6 md:px-8 py-8">
        {/* Patient header strip — avatar + name + age + diagnosis so the
            reader knows whose clinical analysis they're looking at without
            needing to navigate back to the profile. */}
        <div className="max-w-[1600px] mx-auto mb-6 flex items-center gap-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`https://api.dicebear.com/7.x/lorelei/svg?seed=${patient.id}&backgroundColor=fde68a,fcd34d,fbbf24&backgroundType=gradientLinear&hair=variant20,variant21,variant22,variant23,variant24,variant25,variant26,variant27,variant28,variant29,variant30,variant31,variant32,variant33,variant34,variant35,variant36,variant37,variant38,variant39,variant40,variant41,variant42,variant43,variant44,variant45,variant46,variant47&earringsProbability=60`}
            alt={`${patient.persona_name} avatar`}
            className="w-14 h-14 rounded-full border-2 border-white shadow-sm bg-amber-50"
          />
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
              {patient.persona_name}
            </h1>
            <p className="text-sm text-muted-foreground">
              Age {patient.age} · {patient.indication}
            </p>
          </div>
        </div>

        {/* The clinical analysis report. */}
        <div
          ref={reportRef}
          className="max-w-[1600px] mx-auto scroll-mt-6"
        >
          {analysis.isLoading ? (
            <div className="min-h-[60vh] flex items-center justify-center">
              <div className="flex flex-col items-center gap-3 text-muted-foreground">
                <span
                  className="inline-block w-6 h-6 rounded-full border-2 border-amber-300 border-t-amber-500 animate-spin"
                  aria-hidden
                />
                <p className="text-sm">Running the analysis…</p>
              </div>
            </div>
          ) : analysis.isError ? (
            <div className="min-h-[60vh] flex items-center justify-center">
              <p className="text-sm text-red-600 max-w-md text-center">
                Couldn&apos;t run the analysis:{" "}
                {(analysis.error as Error).message}
              </p>
            </div>
          ) : analysis.data ? (
            <ResultsReport
              result={analysis.data}
              patient={patient}
              scarPrefill={scarPrefill}
              recordRefs={recordRefs}
            />
          ) : null}
        </div>
      </main>
    </div>
  );
}

function CenteredMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-[70vh] flex items-center justify-center bg-white px-6">
      <div className="text-center max-w-md">{children}</div>
    </div>
  );
}
