"use client";

import type { MorphologyMatch, MorphologyResult } from "@/lib/types";

interface Props {
  result: MorphologyResult;
}

export function CellGrid({ result }: Props) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <CellTile
        title="DMSO control"
        subtitle="baseline"
        imageUrl={result.control_url}
        similarity={null}
      />
      {result.matches.slice(0, 7).map((m) => (
        <CellTile
          key={m.broad_sample_id + m.rank}
          title={m.compound_name ?? m.broad_sample_id}
          subtitle={`${m.cell_line}${m.perturbation_dose_um ? ` · ${m.perturbation_dose_um} µM` : ""}`}
          imageUrl={m.image_url}
          similarity={m.similarity}
        />
      ))}
    </div>
  );
}

function CellTile({
  title,
  subtitle,
  imageUrl,
  similarity,
}: {
  title: string;
  subtitle: string;
  imageUrl: string;
  similarity: number | null;
}) {
  return (
    <figure className="border rounded overflow-hidden bg-white">
      <div className="aspect-[3/2] bg-slate-900">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={imageUrl} alt={title} className="w-full h-full object-cover" />
      </div>
      <figcaption className="p-2 text-xs">
        <div className="font-medium truncate" title={title}>
          {title}
        </div>
        <div className="text-gray-500 truncate">{subtitle}</div>
        {similarity !== null ? (
          <div className="text-gray-700 mt-0.5">sim {similarity.toFixed(3)}</div>
        ) : null}
      </figcaption>
    </figure>
  );
}

export function matchesSummary(matches: MorphologyMatch[]): string {
  if (matches.length === 0) return "no matches";
  const top = matches[0];
  return `top: ${top.compound_name ?? top.broad_sample_id} (${top.similarity.toFixed(3)})`;
}
