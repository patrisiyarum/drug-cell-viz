"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { JobRead } from "@/lib/types";

interface Props {
  onSubmitted: (job: JobRead) => void;
}

export function DrugInputForm({ onSubmitted }: Props) {
  const [smiles, setSmiles] = useState("CC1=C(C=C(C=C1)NC(=O)C2=CC=C(C=C2)CN3CCN(CC3)C)NC4=NC=CC(=N4)C5=CN=CC=C5");
  const [uniprotId, setUniprotId] = useState("P00519");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const job = await api.createJob({ smiles, uniprot_id: uniprotId, kind: "combined" });
      onSubmitted(job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "submission failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4 max-w-2xl">
      <label className="block">
        <span className="block text-sm font-medium">SMILES</span>
        <input
          className="mt-1 w-full border rounded px-3 py-2 font-mono text-sm"
          value={smiles}
          onChange={(e) => setSmiles(e.target.value)}
          required
          maxLength={500}
        />
      </label>
      <label className="block">
        <span className="block text-sm font-medium">UniProt ID</span>
        <input
          className="mt-1 w-full border rounded px-3 py-2 font-mono text-sm"
          value={uniprotId}
          onChange={(e) => setUniprotId(e.target.value.toUpperCase())}
          required
          pattern="[A-Z0-9]{6,10}"
        />
      </label>
      <button
        type="submit"
        disabled={submitting}
        className="px-4 py-2 rounded bg-black text-white disabled:opacity-50"
      >
        {submitting ? "Submitting…" : "Run analysis"}
      </button>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
    </form>
  );
}
