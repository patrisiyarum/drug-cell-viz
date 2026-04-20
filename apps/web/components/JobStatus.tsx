"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { JobRead } from "@/lib/types";

interface Props {
  jobId: string;
  onJob?: (job: JobRead) => void;
}

export function useJobQuery(jobId: string | null) {
  return useQuery<JobRead>({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      if (status === "completed" || status === "failed") return false;
      return 2000;
    },
  });
}

export function JobStatusBanner({ jobId }: Props) {
  const { data: job, isLoading, isError, error } = useJobQuery(jobId);

  if (isLoading) return <div className="text-sm text-gray-500">Submitting…</div>;
  if (isError)
    return <div className="text-sm text-red-600">{(error as Error).message}</div>;
  if (!job) return null;

  return (
    <div className="text-sm rounded border px-3 py-2 bg-white">
      <span className="font-mono">{job.id.slice(0, 8)}</span>
      <span className="mx-2">·</span>
      <span className="font-medium">{job.status}</span>
      {job.error ? (
        <span className="ml-3 text-red-600">error: {job.error}</span>
      ) : null}
      {job.status === "completed" ? (
        <a
          href={api.exportUrl(job.id)}
          className="ml-4 underline text-blue-600"
        >
          export .zip
        </a>
      ) : null}
    </div>
  );
}
