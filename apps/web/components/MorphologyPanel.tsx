"use client";

import { useQuery } from "@tanstack/react-query";

import { CellGrid } from "./CellGrid";
import { api } from "@/lib/api";
import type { MorphologyResult } from "@/lib/types";

interface Props {
  resultId: string;
}

export function MorphologyPanel({ resultId }: Props) {
  const { data, isLoading, isError, error } = useQuery<MorphologyResult>({
    queryKey: ["morphology", resultId],
    queryFn: () => api.getMorphology(resultId),
  });

  if (isLoading)
    return <div className="text-sm text-gray-500">Loading morphology matches…</div>;
  if (isError)
    return <div className="text-sm text-red-600">{(error as Error).message}</div>;
  if (!data) return null;

  return (
    <div className="space-y-3">
      <div className="text-xs text-gray-600">
        Query fingerprint: <span className="font-mono">{data.query_fingerprint.slice(0, 16)}…</span>
      </div>
      <CellGrid result={data} />
    </div>
  );
}
