"use client";

import { MolViewer } from "./MolViewer";
import { PlainLanguageExplainer } from "./PlainLanguageExplainer";
import type { AnalysisResult, HeadlineSeverity, PGxVerdict, PocketResidue } from "@/lib/bc-types";

interface Props {
  result: AnalysisResult;
}

export function AnalysisResultPanel({ result }: Props) {
  const pdbUrl = result.pose_pdb_url ?? result.protein_pdb_url;
  const highlights = result.pocket_residues.map((r) => ({
    position: r.position,
    inPocket: r.in_pocket,
  }));

  return (
    <div className="space-y-5">
      <HeadlineCard
        text={result.headline}
        severity={result.headline_severity}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <section className="space-y-3">
          <h3 className="font-medium text-sm">Pharmacogenomic evidence</h3>
          {result.pgx_verdicts.length > 0 ? (
            result.pgx_verdicts.map((v, i) => <PGxCard key={i} verdict={v} />)
          ) : (
            <div className="text-sm text-gray-500 p-3 border rounded bg-white">
              No curated drug-gene-variant rule matched your selection for this drug. The
              structural view below is informational only.
            </div>
          )}

          {result.pocket_residues.length > 0 ? (
            <PocketTable residues={result.pocket_residues} targetGene={result.target_gene} />
          ) : null}
        </section>

        <section className="space-y-2">
          <h3 className="font-medium text-sm">
            3D structure — {result.drug_name} on {result.target_gene}
          </h3>
          <div className="h-[420px] border rounded bg-white overflow-hidden relative">
            <MolViewer pdbUrl={pdbUrl} highlights={highlights} />
            <ViewerLegend hasVariants={highlights.length > 0} />
          </div>
          <p className="text-xs text-gray-500">
            Zoomed in automatically on the drug binding site. You can rotate the view by
            click-dragging and zoom with the scroll wheel.
          </p>
        </section>
      </div>

      <section className="space-y-2">
        <h3 className="font-medium text-sm">Plain-English explainer</h3>
        <PlainLanguageExplainer plain={result.plain_language} />
      </section>

      <DisclaimerBox items={result.disclaimers} />
    </div>
  );
}

function HeadlineCard({
  text,
  severity,
}: {
  text: string;
  severity: HeadlineSeverity;
}) {
  const styles: Record<HeadlineSeverity, string> = {
    benefit: "bg-green-50 border-green-300 text-green-900",
    info: "bg-slate-50 border-slate-300 text-slate-900",
    caution: "bg-amber-50 border-amber-300 text-amber-900",
    warning: "bg-orange-50 border-orange-300 text-orange-900",
    contraindicated: "bg-red-50 border-red-300 text-red-900",
  };
  return (
    <div className={`border rounded-md px-4 py-3 ${styles[severity]}`}>
      <div className="text-xs font-semibold uppercase tracking-wide opacity-70">
        Summary
      </div>
      <div className="text-base font-medium mt-0.5">{text}</div>
    </div>
  );
}

function PGxCard({ verdict }: { verdict: PGxVerdict }) {
  return (
    <div className="border rounded bg-white p-3 text-sm space-y-1">
      <div className="flex items-start gap-2 flex-wrap">
        <span className="font-medium">{verdict.drug_name}</span>
        <span className="text-gray-400">×</span>
        <span className="font-mono text-xs bg-slate-100 px-1.5 py-0.5 rounded">
          {verdict.variant_label}
        </span>
        <span className="text-xs text-gray-500">({verdict.zygosity})</span>
        <span className="ml-auto px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-100 text-blue-800">
          Evidence {verdict.evidence_level}
        </span>
      </div>
      <div className="text-xs text-gray-700">
        <span className="font-medium">Phenotype:</span> {verdict.phenotype}
      </div>
      <div className="text-sm text-gray-800">{verdict.recommendation}</div>
      <div className="text-xs text-gray-500 italic">{verdict.source}</div>
    </div>
  );
}

function PocketTable({
  residues,
  targetGene,
}: {
  residues: PocketResidue[];
  targetGene: string;
}) {
  return (
    <div className="border rounded bg-white p-3 text-xs">
      <div className="font-medium mb-2">
        Structural view — variants mapped on {targetGene}
      </div>
      <table className="w-full">
        <thead>
          <tr className="text-left text-gray-500 border-b">
            <th className="py-1">Residue</th>
            <th className="py-1">WT AA</th>
            <th className="py-1">Distance to ligand</th>
            <th className="py-1">In pocket?</th>
          </tr>
        </thead>
        <tbody>
          {residues.map((r, i) => (
            <tr key={i} className="border-b last:border-b-0">
              <td className="py-1 font-mono">{r.position}</td>
              <td className="py-1 font-mono">{r.wildtype_aa ?? "?"}</td>
              <td className="py-1">
                {r.min_distance_to_ligand_angstrom !== null
                  ? `${r.min_distance_to_ligand_angstrom.toFixed(2)} Å`
                  : "—"}
              </td>
              <td className="py-1">
                {r.in_pocket ? (
                  <span className="text-red-700 font-medium">Yes</span>
                ) : (
                  <span className="text-gray-500">No</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ViewerLegend({ hasVariants }: { hasVariants: boolean }) {
  // Absolute-positioned legend overlay so a non-specialist viewer knows what
  // each color on the 3D scene represents.
  return (
    <div className="absolute top-2 left-2 bg-white/95 backdrop-blur-sm border rounded-md px-3 py-2 text-[11px] space-y-1 shadow-sm pointer-events-none">
      <div className="font-semibold text-gray-700 uppercase tracking-wide text-[10px]">
        Legend
      </div>
      <LegendRow color="bg-slate-400" label="Protein (target in your cells)" />
      <LegendRow color="bg-pink-500" label="Drug molecule" />
      {hasVariants ? (
        <LegendRow color="bg-yellow-400" label="Your variant residue" />
      ) : null}
    </div>
  );
}

function LegendRow({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5 text-gray-800">
      <span className={`inline-block w-2.5 h-2.5 rounded-full ${color}`} aria-hidden />
      <span>{label}</span>
    </div>
  );
}

function DisclaimerBox({ items }: { items: string[] }) {
  return (
    <aside className="border-l-4 border-red-600 bg-red-50 rounded-r p-4 text-xs space-y-1">
      <div className="font-semibold text-red-900">Important — read before using this output</div>
      <ul className="list-disc ml-4 text-red-900 space-y-0.5">
        {items.map((d, i) => (
          <li key={i}>{d}</li>
        ))}
      </ul>
    </aside>
  );
}
