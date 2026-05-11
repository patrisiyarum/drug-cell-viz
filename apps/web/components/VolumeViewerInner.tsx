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

    const nv = new Niivue({
      loadingText: "Loading CT volume",
      backColor: [0, 0, 0, 1],
      show3Dcrosshair: false,
      // Hide niivue's 2D slice crosshair entirely — width=0 removes the
      // red lines, transparent color is a belt-and-braces fallback in
      // case a future niivue version draws on width=0. The slideshow
      // shows a single fixed axial slice, so the dragable crosshair UI
      // would just be a non-functional distraction.
      crosshairWidth: 0,
      crosshairColor: [0, 0, 0, 0],
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
          cal_min: huWindow[0],
          cal_max: huWindow[1],
          colormap: "gray",
          opacity: 1.0,
        },
      ]);
      if (cancelled) return;

      // SLICE_TYPE.AXIAL (value 0) = single big axial slice that fills the
      // canvas. Multiplanar (value 3) was rendering as four small panels
      // and looked "shrunk" inside the slideshow card.
      nv.setSliceType(0);
      // High-DPI canvases need niivue to recompute its drawing buffer. Run
      // it once after load so the initial render is sharp on Retina screens.
      nv.resizeListener();
    }

    run().catch((e) => {
      // eslint-disable-next-line no-console
      console.warn("niivue volume load failed", e);
    });

    // Keep the canvas resolution in sync when the parent container resizes
    // (slideshow tab switches, layout changes, window resize). Without this
    // the canvas keeps its initial CSS-pixel size and stretches blurrily.
    const ro = new ResizeObserver(() => {
      nv.resizeListener();
    });
    if (canvasRef.current) ro.observe(canvasRef.current);

    return () => {
      cancelled = true;
      ro.disconnect();
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
