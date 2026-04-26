"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FlaskConical, Trash2, X } from "lucide-react";

import { MolViewer } from "@/components/MolViewer";
import { api, type CandidateScore, type ScreeningResponse } from "@/lib/api";
import type { Catalog } from "@/lib/bc-types";

/**
 * Virtual-screening playground.
 *
 * Pick an HR-panel target (BRCA1, BRCA2, PARP1, ESR1, CDK4/6, PIK3CA, …),
 * paste a short list of candidate SMILES (one per line, optional name and
 * id), and see them ranked by a composite pocket-fit + chemical-similarity
 * score. This mirrors the core Bioptic product story in miniature: score
 * compounds against a pocket on a computer before ever touching the lab.
 */

interface CandidateRow {
  id: string;
  name: string;
  smiles: string;
}

const STARTER_LIBRARIES: Record<string, CandidateRow[]> = {
  PARP1: [
    { id: "olaparib", name: "Olaparib", smiles: "C1CC1C(=O)N2CCN(CC2)C(=O)C3=CC=CC(=C3CC4=NNC(=O)C5=CC=CC=C54)F" },
    { id: "niraparib", name: "Niraparib", smiles: "C1CC(C1)N2CCC(CC2)C3=CC4=C(C=C3)C=CC=C4C(=O)N" },
    { id: "talazoparib", name: "Talazoparib", smiles: "C1CC2=C(C1=O)C3=CC(=CC=C3N=C2C4=CC=C(C=C4)F)C5=NNC=N5" },
    { id: "rucaparib", name: "Rucaparib", smiles: "CNCC1=CC=C(C=C1)C2=C3C(=CC=C2F)C(=O)NCC3" },
    { id: "aspirin", name: "Aspirin (negative control)", smiles: "CC(=O)Oc1ccccc1C(=O)O" },
  ],
  ESR1: [
    { id: "tamoxifen", name: "Tamoxifen", smiles: "CCC(=C(c1ccccc1)c1ccc(OCCN(C)C)cc1)c1ccccc1" },
    { id: "fulvestrant", name: "Fulvestrant", smiles: "CC1CC2C3CCC4=CC(=CC=C4C3CCC2(C1O)CCCCCCCCCS(=O)CCCC(F)(F)C(F)(F)F)O" },
    { id: "elacestrant", name: "Elacestrant", smiles: "CCc1ccc(CCN2CCC[C@@H]2[C@@H](O)c2ccc3OCCc3c2)cc1" },
    { id: "aspirin", name: "Aspirin (negative control)", smiles: "CC(=O)Oc1ccccc1C(=O)O" },
  ],
  CDK4: [
    { id: "palbociclib", name: "Palbociclib", smiles: "CC(=O)C1=C(C)C2=CN=C(NC3=NC=C(C=C3)N3CCNCC3)N=C2N(C2CCCC2)C1=O" },
    { id: "ribociclib", name: "Ribociclib", smiles: "CC1(C)c2nc3c(cnc(Nc4ccc(N5CCNCC5)cn4)n3)cc2N(C)C1=O" },
    { id: "abemaciclib", name: "Abemaciclib", smiles: "CCN1CCN(Cc2ccc(Nc3ncc(F)c(-c4cc5cc(F)ccc5[nH]4)n3)nc2C)CC1" },
    { id: "aspirin", name: "Aspirin (negative control)", smiles: "CC(=O)Oc1ccccc1C(=O)O" },
  ],
};

export default function ScreenPage() {
  const { data: catalog } = useQuery<Catalog>({
    queryKey: ["bc-catalog"],
    queryFn: () => api.getCatalog(),
  });

  const [targetGene, setTargetGene] = useState<string>("PARP1");
  const [rawSmiles, setRawSmiles] = useState<string>("");
  const [result, setResult] = useState<ScreeningResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Which candidate's 3D binding pose is currently being inspected. Auto-
  // selects the top ranked after a successful run.
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Scroll the 3D pose + ranked table into view as soon as a screening lands
  // so the user doesn't have to hunt for the results below the fold.
  const resultsRef = useRef<HTMLDivElement | null>(null);
  const poseRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (result && resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    // Only fire when a new run lands — keyed on ranked list length + target,
    // so clicking a row inside the existing result doesn't re-scroll the page.
  }, [result?.target_gene, result?.ranked.length]);

  // Clicking a row in the ranking table changes selectedId; scroll the 3D
  // pose card (which sits above the table) back into view so the user sees
  // the new compound bound without manually scrolling up.
  function handleSelect(id: string) {
    setSelectedId(id);
    // rAF so the DOM has committed the selected-row style before we scroll.
    requestAnimationFrame(() => {
      poseRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  // Seed the textarea with a starter library whenever the target changes and
  // the user hasn't typed anything.
  useEffect(() => {
    if (rawSmiles.trim()) return;
    const starter = STARTER_LIBRARIES[targetGene];
    if (starter) {
      setRawSmiles(starter.map((c) => `${c.smiles}\t${c.name}`).join("\n"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetGene]);

  const parsed = useMemo<CandidateRow[]>(() => {
    return parseSmilesList(rawSmiles);
  }, [rawSmiles]);

  async function onRun() {
    if (parsed.length === 0) {
      setError("add at least one SMILES");
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const resp = await api.runScreening({
        target_gene: targetGene,
        candidates: parsed,
      });
      setResult(resp);
      // Default to inspecting the top-ranked candidate's binding pose.
      setSelectedId(resp.ranked[0]?.candidate_id ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "screening failed");
    } finally {
      setRunning(false);
    }
  }

  function onClear() {
    setResult(null);
    setRawSmiles("");
    setSelectedId(null);
  }

  const screenableTargets = [
    "PARP1",
    "ESR1",
    "ERBB2",
    "PIK3CA",
    "CDK4",
    "CDK6",
    "CYP19A1",
    "AKT1",
    "BRCA1",
    "BRCA2",
  ];

  return (
    <div className="flex flex-col bg-white min-h-screen">
      <header className="border-b bg-card">
        <div className="max-w-[1600px] mx-auto px-6 md:px-8 py-5 flex items-center justify-between gap-4">
          <Link href="/" className="text-muted-foreground hover:text-foreground text-sm">
            ← Back
          </Link>
          <div className="flex items-center gap-4 text-sm">
            <Link href="/demo" className="text-muted-foreground hover:text-foreground">
              Cases
            </Link>
            <Link href="/build" className="text-muted-foreground hover:text-foreground">
              Build your own
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1 px-6 md:px-8 py-10 md:py-14">
        <div className="max-w-4xl mx-auto space-y-8">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-primary">
              <FlaskConical className="w-5 h-5" aria-hidden />
              <span className="text-xs font-semibold uppercase tracking-wide">
                Clinical drug screening
              </span>
            </div>
            <h1 className="text-3xl md:text-4xl font-semibold">
              Find candidate drugs against an HR-pathway target
            </h1>
            <p className="text-muted-foreground">
              For oncology teams evaluating compounds for HRD-positive cancers.
              Pick the target, paste candidate SMILES. Ranked by 60% pocket fit
              + 40% similarity to known binders.
            </p>
            {/* Kintsugi seam */}
            <div className="h-px max-w-md bg-gradient-to-r from-amber-400/40 via-amber-500 to-amber-400/40 mt-4" />
          </div>

          <section className="bg-card border rounded-2xl p-5 md:p-6 space-y-4">
            <div>
              <label className="text-sm font-medium mb-1 block">
                Target gene
              </label>
              <select
                className="w-full md:w-80 border rounded-lg px-3 py-2 text-sm bg-white"
                value={targetGene}
                onChange={(e) => {
                  setTargetGene(e.target.value);
                  setResult(null);
                  setRawSmiles("");
                }}
              >
                {screenableTargets.map((sym) => {
                  const gene = catalog?.genes.find((g) => g.symbol === sym);
                  return (
                    <option key={sym} value={sym}>
                      {sym}
                      {gene ? ` (${gene.name})` : ""}
                    </option>
                  );
                })}
              </select>
            </div>

            <div>
              <label className="text-sm font-medium mb-1 block">
                Candidate compounds
                <span className="text-xs text-muted-foreground ml-2">
                  one per line · format: <code>SMILES</code> or <code>SMILES</code>{" "}
                  <kbd>\t</kbd> <code>name</code>
                </span>
              </label>
              <textarea
                value={rawSmiles}
                onChange={(e) => setRawSmiles(e.target.value)}
                rows={10}
                placeholder="O=C(N1CCN(CC1)C(=O)c1cc2c(...))...    Olaparib"
                className="w-full text-xs font-mono border rounded-lg p-3 bg-white"
              />
              <div className="text-xs text-muted-foreground mt-1">
                {parsed.length} compound{parsed.length === 1 ? "" : "s"} parsed
              </div>
            </div>

            <div className="flex items-center gap-3 flex-wrap pt-2 border-t">
              <button
                type="button"
                onClick={onRun}
                disabled={running || parsed.length === 0}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {running ? "Scoring…" : `Screen ${parsed.length} compound${parsed.length === 1 ? "" : "s"}`}
              </button>
              <button
                type="button"
                onClick={onClear}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-xs text-muted-foreground hover:text-foreground"
              >
                <Trash2 className="w-3.5 h-3.5" aria-hidden /> Clear
              </button>
              {error ? <span className="text-sm text-red-600">{error}</span> : null}
            </div>
          </section>

          {result ? (
            <div ref={resultsRef} className="space-y-6 scroll-mt-6">
              <div ref={poseRef} className="scroll-mt-6">
                <BindingPoseCard
                  result={result}
                  selectedId={selectedId}
                  onClose={() => setSelectedId(null)}
                />
              </div>
              <ResultsTable
                result={result}
                selectedId={selectedId}
                onSelect={handleSelect}
              />
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}

function ResultsTable({
  result,
  selectedId,
  onSelect,
}: {
  result: ScreeningResponse;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="bg-card border rounded-2xl overflow-hidden">
      <div className="p-5 md:p-6 border-b space-y-1">
        <h2 className="text-lg md:text-xl font-semibold">
          Ranked against {result.target_gene}{" "}
          <span className="text-xs font-normal text-muted-foreground">
            ({result.target_uniprot})
          </span>
        </h2>
        <p className="text-xs text-muted-foreground">
          Reference binders used for chemical similarity:{" "}
          {result.reference_binders.length > 0
            ? result.reference_binders.join(", ")
            : "none (BRCA1/BRCA2 have no druggable pocket; scoring falls back to pocket fit only)"}
          {" · "}
          pocket radius = {result.pocket_radius_angstrom} Å · click a row to
          see the 3D binding pose
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-xs uppercase tracking-wide">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">Rank</th>
              <th className="px-4 py-3 text-left font-semibold">Compound</th>
              <th className="px-4 py-3 text-right font-semibold">Fit score</th>
              <th className="px-4 py-3 text-right font-semibold">Pocket fit</th>
              <th className="px-4 py-3 text-right font-semibold">Chem sim.</th>
              <th className="px-4 py-3 text-left font-semibold">Closest ref</th>
            </tr>
          </thead>
          <tbody>
            {result.ranked.map((s) => (
              <ResultRow
                key={s.candidate_id}
                s={s}
                selected={s.candidate_id === selectedId}
                onSelect={() => onSelect(s.candidate_id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ResultRow({
  s,
  selected,
  onSelect,
}: {
  s: CandidateScore;
  selected: boolean;
  onSelect: () => void;
}) {
  const base = selected
    ? "bg-primary/10"
    : s.rank === 1
      ? "bg-success/5"
      : "";
  return (
    <tr
      className={`border-t cursor-pointer hover:bg-muted/40 transition-colors ${base}`}
      onClick={onSelect}
    >
      <td className="px-4 py-3 font-semibold">{s.rank}</td>
      <td className="px-4 py-3">
        <div className="font-medium">{s.name}</div>
        <div className="text-[10px] text-muted-foreground font-mono truncate max-w-[260px]">
          {s.smiles}
        </div>
      </td>
      <td className="px-4 py-3 text-right font-semibold">
        <ScoreBar score={s.fit_score} />
      </td>
      <td className="px-4 py-3 text-right text-muted-foreground">
        {(s.pocket_fit * 100).toFixed(0)}%
      </td>
      <td className="px-4 py-3 text-right text-muted-foreground">
        {(s.chem_similarity * 100).toFixed(0)}%
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground">
        {s.closest_reference ?? "n/a"}
      </td>
    </tr>
  );
}

/**
 * 3D view of the selected candidate's docked binding pose. Falls back to the
 * apo AlphaFold structure when the per-candidate pose URL is missing (e.g. a
 * transient storage failure during screening).
 */
function BindingPoseCard({
  result,
  selectedId,
  onClose,
}: {
  result: ScreeningResponse;
  selectedId: string | null;
  onClose: () => void;
}) {
  if (!selectedId) return null;
  const selected = result.ranked.find((s) => s.candidate_id === selectedId);
  if (!selected) return null;
  const pdbUrl = selected.pose_pdb_url ?? result.protein_pdb_url;
  const isPose = Boolean(selected.pose_pdb_url);

  return (
    <section className="bg-card border rounded-2xl overflow-hidden">
      <div className="p-5 md:p-6 border-b flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            3D binding pose · rank {selected.rank}
          </div>
          <h3 className="text-lg font-semibold">
            {selected.name} bound to {result.target_gene}
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Fit score {selected.fit_score.toFixed(2)} · pocket fit{" "}
            {(selected.pocket_fit * 100).toFixed(0)}% ·{" "}
            {selected.heavy_atom_count} heavy atoms
            {!isPose ? (
              <>
                {" · "}
                <span className="text-warning">
                  pose unavailable, showing apo structure
                </span>
              </>
            ) : null}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          aria-label="Close 3D viewer"
        >
          <X className="w-4 h-4" aria-hidden /> Close
        </button>
      </div>
      <div className="relative h-[480px] bg-slate-50">
        {/* key={pdbUrl} forces Mol* to fully remount whenever the user picks
             a different candidate row. Without it, some Mol* plugin state
             caches the first pose and subsequent selections show the same
             structure — rank 1 stayed visible even after clicking rank 2+. */}
        <MolViewer key={pdbUrl} pdbUrl={pdbUrl} />
        <div className="absolute top-2 left-2 bg-white/95 backdrop-blur-sm border rounded-md px-3 py-2 text-[11px] space-y-1 shadow-sm pointer-events-none">
          <div className="font-semibold text-muted-foreground uppercase tracking-wide text-[10px]">
            Legend
          </div>
          <LegendRow color="bg-slate-400" label={`${result.target_gene} protein`} />
          {isPose ? (
            <LegendRow color="bg-pink-500" label={`${selected.name} ligand`} />
          ) : null}
        </div>
      </div>
    </section>
  );
}

function LegendRow({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        className={`inline-block w-2.5 h-2.5 rounded-full ${color}`}
        aria-hidden
      />
      <span>{label}</span>
    </div>
  );
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score * 100));
  return (
    <div className="inline-flex items-center gap-2">
      <div className="w-20 h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full bg-primary"
          style={{ width: `${pct}%` }}
          aria-hidden
        />
      </div>
      <span>{score.toFixed(2)}</span>
    </div>
  );
}

/**
 * Parse a newline-separated list of candidates.
 *
 * Accepts either:
 *   SMILES
 *   SMILES<TAB>Name
 *   SMILES<TAB>Name<TAB>Id
 *
 * Auto-generates an id from the name (or "cpd_N") when not supplied.
 */
function parseSmilesList(raw: string): CandidateRow[] {
  const out: CandidateRow[] = [];
  let n = 0;
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const parts = trimmed.split(/\t+/);
    const smiles = parts[0]?.trim();
    if (!smiles) continue;
    n += 1;
    const name = parts[1]?.trim() ?? `Compound ${n}`;
    const id =
      parts[2]?.trim() ??
      (name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") ||
        `cpd_${n}`);
    out.push({ id, name, smiles });
  }
  return out;
}
