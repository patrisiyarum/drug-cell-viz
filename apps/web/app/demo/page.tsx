"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, User } from "lucide-react";

import { api } from "@/lib/api";
import type { DemoPatient, Demos } from "@/lib/bc-types";

export default function PatientsListPage() {
  const { data, isLoading } = useQuery<Demos>({
    queryKey: ["bc-demos"],
    queryFn: () => api.getDemos(),
  });

  return (
    <div className="min-h-screen flex flex-col bg-white">
      <header className="border-b bg-card">
        <div className="max-w-6xl mx-auto px-6 md:px-8 py-6">
          <Link
            href="/"
            className="text-muted-foreground hover:text-foreground transition-colors text-sm"
          >
            ← Back
          </Link>
        </div>
      </header>

      <main className="flex-1 px-6 md:px-8 py-16">
        <div className="max-w-3xl mx-auto space-y-10">
          <div className="space-y-3 text-center">
            <h1 className="text-3xl md:text-4xl font-semibold">Patient profiles</h1>
            <p className="text-base text-muted-foreground">Pick a profile.</p>
            <div className="h-px max-w-xs mx-auto bg-gradient-to-r from-transparent via-amber-500 to-transparent mt-4" />
          </div>

          {isLoading ? (
            <div className="text-center text-sm text-muted-foreground">Loading.</div>
          ) : null}

          <div className="grid gap-4">
            {data?.patients.map((p) => <ProfileCard key={p.id} patient={p} />)}
          </div>
        </div>
      </main>

      <footer className="border-t bg-card">
        <div className="max-w-6xl mx-auto px-6 md:px-8 py-6 text-center">
          <p className="text-xs text-muted-foreground">For education only. Not medical advice.</p>
        </div>
      </footer>
    </div>
  );
}

function ProfileCard({ patient }: { patient: DemoPatient }) {
  return (
    <Link
      href={`/patient/${patient.id}`}
      className="group bg-card border rounded-2xl p-5 md:p-6 hover:border-primary/50 hover:shadow-sm transition-all"
    >
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center flex-shrink-0">
          <User className="w-5 h-5 text-muted-foreground" />
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-semibold group-hover:text-primary transition-colors">
            {patient.persona_name}
          </h2>
          <p className="text-sm text-muted-foreground">
            Age {patient.age} · {patient.indication}
          </p>
        </div>
        <ArrowRight className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors flex-shrink-0" />
      </div>
    </Link>
  );
}
