"use client";

import { useEffect, useRef } from "react";
import { Niivue } from "@niivue/niivue";

/**
 * Volumetric CT viewer powered by niivue (WebGL2 volume rendering).
 *
 * Loads a NIfTI (`.nii` or `.nii.gz`) URL and renders it as an interactive
 * 3D volume: click-drag to rotate, scroll to zoom. HU windowing is applied
 * via cal_min / cal_max on the loaded volume so soft tissue (the tumor we
 * care about) stands out above bone + below air.
 *
 * This is the same volume the radiogenomics model consumes — no lossy
 * surface extraction, no isosurface, just the full HU density cube rendered
 * with an opacity transfer function.
 *
 * Dynamically imported from VolumeViewer.tsx with ssr: false because niivue
 * requires a real WebGL2 canvas that Next.js server render can't provide.
 */
interface Props {
  volumeUrl: string;
  huWindow?: [number, number];
}

export default function VolumeViewerInner({
  volumeUrl,
  huWindow = [-200, 250],
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const nvRef = useRef<Niivue | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    let cancelled = false;

    // Niivue's constructor creates a WebGL2 context. Multi-planar slice
    // view (axial + sagittal + coronal) is what radiologists actually use
    // to read CTs; pure volumetric rendering of a synthetic scan hides the
    // tumor inside an opaque body blob. Crosshair on so the three panels
    // stay coordinated when the patient clicks to navigate.
    const nv = new Niivue({
      loadingText: "Loading CT volume",
      backColor: [0, 0, 0, 1],
      show3Dcrosshair: true,
      crosshairWidth: 1,
      crosshairColor: [1, 0.6, 0, 0.8],
      dragAndDropEnabled: false,
      isColorbar: false,
      isOrientCube: false,
      isRadiologicalConvention: true,
    });
    nvRef.current = nv;

    async function run() {
      const canvas = canvasRef.current;
      if (!canvas) return;

      await nv.attachToCanvas(canvas);
      if (cancelled) return;

      await nv.loadVolumes([
        {
          url: volumeUrl,
          // HU window equivalent to the training preprocess pipeline so the
          // viewer highlights the same tissue band the model is looking at.
          cal_min: huWindow[0],
          cal_max: huWindow[1],
          colormap: "gray",
          opacity: 1.0,
        },
      ]);
      if (cancelled) return;

      // SLICE_TYPE.MULTIPLANAR (value 3) = three orthogonal slice views + a
      // 3D render corner panel. Far more legible than the pure volumetric
      // mode for a small synthetic dataset: each slice plane slices THROUGH
      // the body so the tumor blob is immediately visible in all three.
      nv.setSliceType(3);
    }

    run().catch((e) => {
      // Don't crash the page if WebGL2 is unavailable (old browser / headless
      // CI). Logging is enough — the parent card caption already tells the
      // user this is a research demo.
      // eslint-disable-next-line no-console
      console.warn("niivue volume load failed", e);
    });

    return () => {
      cancelled = true;
      // Niivue doesn't expose an explicit destroy() across all versions; the
      // canvas removal + the WebGL context loss on unmount handle cleanup.
    };
  }, [volumeUrl, huWindow]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full h-full block"
      aria-label="CT volume render"
    />
  );
}
