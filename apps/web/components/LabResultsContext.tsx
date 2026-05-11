"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type {
  CtScanResponse,
  HRDetectResponse,
  HrdScarResponse,
} from "@/lib/api";
import type { Brca1Classification } from "@/lib/bc-types";

/**
 * Live snapshot of every lab tile's most recent output. The lab tiles
 * write to this from inside HrdCard; the WalkthroughChat reads from it
 * to feed Claude actual numbers ("your CT model said 91% p(HRD)") rather
 * than just describing what each tile does.
 *
 * Each field is null until the tile actually runs (or, for tiles that
 * autorun, until the request returns).
 */
export interface LabResultsState {
  ct: CtScanResponse | null;
  scar: HrdScarResponse | null;
  hrdetect: HRDetectResponse | null;
  /** Keyed by HGVS protein notation so multiple BRCA1 variants stack. */
  brca1: Record<string, Brca1Classification>;
}

interface LabResultsContextShape extends LabResultsState {
  setCt: (v: CtScanResponse | null) => void;
  setScar: (v: HrdScarResponse | null) => void;
  setHrdetect: (v: HRDetectResponse | null) => void;
  setBrca1: (hgvs: string, v: Brca1Classification | null) => void;
}

const LabResultsContext = createContext<LabResultsContextShape | null>(null);

export function LabResultsProvider({ children }: { children: ReactNode }) {
  const [ct, setCt] = useState<CtScanResponse | null>(null);
  const [scar, setScar] = useState<HrdScarResponse | null>(null);
  const [hrdetect, setHrdetect] = useState<HRDetectResponse | null>(null);
  const [brca1Map, setBrca1Map] = useState<
    Record<string, Brca1Classification>
  >({});

  const setBrca1 = useCallback(
    (hgvs: string, v: Brca1Classification | null) => {
      setBrca1Map((m) => {
        if (!v) {
          if (!(hgvs in m)) return m;
          const next = { ...m };
          delete next[hgvs];
          return next;
        }
        if (m[hgvs] === v) return m;
        return { ...m, [hgvs]: v };
      });
    },
    [],
  );

  const value = useMemo<LabResultsContextShape>(
    () => ({
      ct,
      scar,
      hrdetect,
      brca1: brca1Map,
      setCt,
      setScar,
      setHrdetect,
      setBrca1,
    }),
    [ct, scar, hrdetect, brca1Map, setBrca1],
  );

  return (
    <LabResultsContext.Provider value={value}>
      {children}
    </LabResultsContext.Provider>
  );
}

const EMPTY: LabResultsState = {
  ct: null,
  scar: null,
  hrdetect: null,
  brca1: {},
};

/** Read-only consumer used by the chat. Falls back to empty when no
 *  provider is mounted (e.g. tests, embedding the chat outside the
 *  results page) so the chat still functions, just without lab data. */
export function useLabResults(): LabResultsState {
  const ctx = useContext(LabResultsContext);
  if (!ctx) return EMPTY;
  const { ct, scar, hrdetect, brca1 } = ctx;
  return { ct, scar, hrdetect, brca1 };
}

/** Writer used by the lab-tile bodies. Returns null when no provider
 *  is mounted; tiles handle that by simply skipping the publish. */
export function useLabResultsWriter() {
  const ctx = useContext(LabResultsContext);
  if (!ctx) return null;
  return {
    setCt: ctx.setCt,
    setScar: ctx.setScar,
    setHrdetect: ctx.setHrdetect,
    setBrca1: ctx.setBrca1,
  };
}
