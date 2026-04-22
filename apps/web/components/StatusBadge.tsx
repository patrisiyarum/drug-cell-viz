"use client";

import { CheckCircle2, AlertCircle, Info } from "lucide-react";
import type { ReactNode } from "react";

export type PatientStatus = "expected" | "reduced" | "dose-adjustment";

interface Props {
  status: PatientStatus;
  children: ReactNode;
}

export function StatusBadge({ status, children }: Props) {
  const config = {
    expected: {
      Icon: CheckCircle2,
      bg: "bg-success/10",
      border: "border-success/30",
      iconColor: "text-success",
    },
    reduced: {
      Icon: AlertCircle,
      bg: "bg-warning/10",
      border: "border-warning/30",
      iconColor: "text-warning",
    },
    "dose-adjustment": {
      Icon: Info,
      bg: "bg-info/10",
      border: "border-info/30",
      iconColor: "text-info",
    },
  }[status];
  const Icon = config.Icon;

  return (
    <div className={`${config.bg} border ${config.border} rounded-2xl p-6 md:p-8`}>
      <div className="flex items-start gap-4">
        <Icon className={`w-7 h-7 ${config.iconColor} flex-shrink-0 mt-1`} aria-hidden />
        <div>
          <h2 className="text-xl md:text-2xl font-semibold mb-2">Bottom line</h2>
          <p className="text-base md:text-lg leading-relaxed">{children}</p>
        </div>
      </div>
    </div>
  );
}
