"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { MolViewer } from "./MolViewer";
import { api } from "@/lib/api";
import type { MolecularResult } from "@/lib/types";

interface Props {
  resultId: string;
}

export function MolecularPanel({ resultId }: Props) {
  const { data, isLoading, isError, error } = useQuery<MolecularResult>({
    queryKey: ["molecular", resultId],
    queryFn: () => api.getMolecular(resultId),
  });
  const [poseIdx, setPoseIdx] = useState(0);

  if (isLoading)
    return <div className="text-sm text-gray-500">Loading docking result…</div>;
  if (isError)
    return <div className="text-sm text-red-600">{(error as Error).message}</div>;
  if (!data) return null;

  const pose = data.poses[poseIdx] ?? data.poses[0];

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 min-h-[400px] border rounded bg-white overflow-hidden">
        {pose ? (
          <MolViewer pdbUrl={pose.pdb_url} />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-sm text-gray-500">
            No poses available.
          </div>
        )}
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs text-gray-700 flex-wrap">
        <span className="font-medium">Source:</span>
        <span>{data.source}</span>
        <span className="mx-2 text-gray-300">|</span>
        <span className="font-medium">Poses:</span>
        {data.poses.map((p, i) => (
          <button
            key={p.rank}
            onClick={() => setPoseIdx(i)}
            className={`px-2 py-0.5 rounded border ${
              i === poseIdx ? "bg-black text-white" : "bg-white text-gray-700"
            }`}
            title={`confidence ${p.confidence.toFixed(3)}`}
          >
            #{p.rank} · {p.confidence.toFixed(2)}
          </button>
        ))}
      </div>
    </div>
  );
}
