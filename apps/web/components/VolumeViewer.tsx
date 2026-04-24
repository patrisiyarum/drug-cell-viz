"use client";

import dynamic from "next/dynamic";

/**
 * Dynamic (SSR-disabled) wrapper around VolumeViewerInner.
 *
 * niivue needs a real WebGL2 context; Next.js server rendering can't provide
 * one, so we lazy-load the viewer only on the client. Same pattern as
 * MolViewer for the Mol* 3D protein viewer.
 */
const VolumeViewerInner = dynamic(() => import("./VolumeViewerInner"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground bg-black">
      Loading CT volume
    </div>
  ),
});

interface Props {
  volumeUrl: string;
  huWindow?: [number, number];
}

export function VolumeViewer(props: Props) {
  return <VolumeViewerInner {...props} />;
}
