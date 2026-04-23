"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, AlertCircle, Info } from "lucide-react";

import { api } from "@/lib/api";
import type { DemoPatient, Demos } from "@/lib/bc-types";

export default function DemoSelectorPage() {
  const { data, isLoading } = useQuery<Demos>({
    queryKey: ["bc-demos"],
    queryFn: () => api.getDemos(),
  });

  return (
    <div className="min-h-screen flex flex-col bg-white">
      <header className="border-b bg-card">
        <div className="max-w-6xl mx-auto px-6 md:px-8 py-6">
          <Link href="/" className="text-muted-foreground hover:text-foreground transition-colors text-sm">
            ← Back
          </Link>
        </div>
      </header>

      <main className="flex-1 px-6 md:px-8 py-16 md:py-20">
        <div className="max-w-4xl mx-auto space-y-12">
          <div className="space-y-3 text-center">
            <h1 className="text-3xl md:text-4xl font-semibold">
              Three examples based on real clinical guidelines.
            </h1>
            <p className="text-lg md:text-xl text-muted-foreground">
              Select a case to see how genetics affects medication.
            </p>
            {data?.note ? (
              <p className="text-xs italic text-muted-foreground max-w-2xl mx-auto pt-2">
                {data.note}
              </p>
            ) : null}
          </div>

          {isLoading ? (
            <div className="text-center text-sm text-muted-foreground">Loading cases…</div>
          ) : null}

          <div className="grid gap-5">
            {data?.patients.map((p) => <CaseCard key={p.id} patient={p} />)}
          </div>
        </div>
      </main>

      <footer className="border-t bg-card">
        <div className="max-w-6xl mx-auto px-6 md:px-8 py-6 flex items-center justify-between flex-wrap gap-4">
          <a
            href="https://cpicpgx.org/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline text-sm"
          >
            Learn about pharmacogenomics at CPIC →
          </a>
          <p className="text-sm text-muted-foreground">For education only. Not medical advice.</p>
        </div>
      </footer>
    </div>
  );
}

function CaseCard({ patient }: { patient: DemoPatient }) {
  const accents: Record<
    string,
    { bg: string; color: string; Icon: typeof CheckCircle2 }
  > = {
    success: { bg: "bg-success/10", color: "text-success", Icon: CheckCircle2 },
    warning: { bg: "bg-warning/10", color: "text-warning", Icon: AlertCircle },
    info: { bg: "bg-info/10", color: "text-info", Icon: Info },
  };
  const cfg = accents[patient.status_color] ?? accents.info;
  const Icon = cfg.Icon;

  return (
    <Link
      href={`/walkthrough/${patient.id}`}
      className="group bg-card border rounded-2xl p-6 md:p-8 hover:border-primary/50 hover:shadow-sm transition-all"
    >
      <div className="flex items-start gap-5 md:gap-6">
        <div
          className={`w-12 h-12 md:w-14 md:h-14 rounded-xl ${cfg.bg} flex items-center justify-center flex-shrink-0`}
        >
          <Icon className={`w-6 h-6 md:w-7 md:h-7 ${cfg.color}`} />
        </div>
        <div className="flex-1 space-y-2 min-w-0">
          <h2 className="text-xl md:text-2xl font-semibold group-hover:text-primary transition-colors">
            {patient.name}
          </h2>
          <p className="text-base md:text-lg text-muted-foreground leading-relaxed">
            {patient.scenario}
          </p>
          <p className="text-xs text-muted-foreground pt-1">
            {patient.persona_name}, {patient.age} · starting {patient.medication_display} for{" "}
            {patient.indication}
          </p>
        </div>
        <ArrowRight className="w-5 h-5 md:w-6 md:h-6 text-muted-foreground group-hover:text-primary transition-colors flex-shrink-0 mt-2" />
      </div>
    </Link>
  );
}
