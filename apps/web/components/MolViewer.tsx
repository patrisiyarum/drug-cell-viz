"use client";

import dynamic from "next/dynamic";

const MolViewerInner = dynamic(() => import("./MolViewerInner"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center text-sm text-gray-500">
      Loading 3D viewer…
    </div>
  ),
});

interface VariantHighlight {
  position: number;
  inPocket: boolean;
}

interface Props {
  pdbUrl: string;
  highlights?: VariantHighlight[];
}

export function MolViewer({ pdbUrl, highlights }: Props) {
  return (
    <div className="w-full h-full">
      <MolViewerInner pdbUrl={pdbUrl} highlights={highlights} />
    </div>
  );
}
