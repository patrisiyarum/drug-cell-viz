"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";

import { api } from "@/lib/api";
import type { DemoPatient, Demos } from "@/lib/bc-types";

function avatarFor(patientId: string): string {
  // Maya, Diana, Priya are all women — pin hair to the feminine-presenting
  // long-hair variants (20+) so the seed-based generator doesn't pick
  // masculine outputs. Seed still drives face shape + accessories.
  const femHair = Array.from({ length: 28 }, (_, i) =>
    `variant${String(i + 20).padStart(2, "0")}`,
  ).join(",");
  const params = new URLSearchParams({
    seed: patientId,
    backgroundColor: "fde68a,fcd34d,fbbf24",
    backgroundType: "gradientLinear",
    hair: femHair,
    earringsProbability: "60",
  });
  return `https://api.dicebear.com/7.x/lorelei/svg?${params.toString()}`;
}

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
      className="group bg-card border rounded-2xl p-5 hover:border-amber-300 hover:shadow-sm transition-all"
    >
      <div className="flex items-center gap-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={avatarFor(patient.id)}
          alt={`${patient.persona_name} avatar`}
          className="w-14 h-14 rounded-full border-2 border-white shadow-sm bg-amber-50 flex-shrink-0"
        />
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
