"use client";

import { useEffect, useRef } from "react";

// Mol* has side effects on import (touches window). This whole module is only
// loaded via `next/dynamic` with ssr: false — keep it that way.
import { createPluginUI } from "molstar/lib/mol-plugin-ui";
import { renderReact18 } from "molstar/lib/mol-plugin-ui/react18";
import { DefaultPluginUISpec } from "molstar/lib/mol-plugin-ui/spec";
import type { PluginUIContext } from "molstar/lib/mol-plugin-ui/context";
import { Script } from "molstar/lib/mol-script/script";
import { StructureSelection } from "molstar/lib/mol-model/structure";
import "molstar/lib/mol-plugin-ui/skin/light.scss";

interface VariantHighlight {
  position: number;
  inPocket: boolean;
}

interface Props {
  pdbUrl: string;
  highlights?: VariantHighlight[];
}

export default function MolViewerInner({ pdbUrl, highlights }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pluginRef = useRef<PluginUIContext | null>(null);

  useEffect(() => {
    let disposed = false;
    const host = containerRef.current;
    if (!host) return;
    const inner = document.createElement("div");
    inner.style.position = "relative";
    inner.style.width = "100%";
    inner.style.height = "100%";
    host.appendChild(inner);

    (async () => {
      const plugin = await createPluginUI({
        target: inner,
        render: renderReact18,
        spec: {
          ...DefaultPluginUISpec(),
          layout: {
            initial: {
              isExpanded: false,
              showControls: false,
              controlsDisplay: "reactive",
            },
          },
        },
      });
      if (disposed) {
        plugin.dispose();
        return;
      }
      pluginRef.current = plugin;

      try {
        const data = await plugin.builders.data.download(
          { url: pdbUrl, isBinary: false },
          { state: { isGhost: true } },
        );
        const trajectory = await plugin.builders.structure.parseTrajectory(data, "pdb");
        await plugin.builders.structure.hierarchy.applyPreset(trajectory, "default");

        if (highlights && highlights.length > 0) {
          await highlightResidues(plugin, highlights);
        }
      } catch (err) {
        console.error("Mol* failed to load structure", err);
      }
    })();

    return () => {
      disposed = true;
      pluginRef.current?.dispose();
      pluginRef.current = null;
      inner.remove();
    };
  }, [pdbUrl, JSON.stringify(highlights ?? [])]);

  return <div ref={containerRef} className="relative w-full h-full" />;
}

async function highlightResidues(
  plugin: PluginUIContext,
  highlights: VariantHighlight[],
): Promise<void> {
  const structureRef = plugin.managers.structure.hierarchy.current.structures[0];
  if (!structureRef?.cell.obj) return;
  const structure = structureRef.cell.obj.data;

  const positions = highlights.map((h) => h.position);

  // Select all variant residues at once — Mol* will paint them with the
  // selection color (bright, high contrast against the default chain colors).
  const selection = Script.getStructureSelection(
    (Q: any) =>
      Q.struct.generator.atomGroups({
        "residue-test": Q.core.set.has([
          Q.set(...positions),
          Q.struct.atomProperty.macromolecular.auth_seq_id(),
        ]),
      }),
    structure,
  );
  const loci = StructureSelection.toLociWithSourceUnits(selection);
  if (loci.elements.length === 0) return;

  plugin.managers.structure.selection.fromLoci("set", loci);
  plugin.managers.camera.focusLoci(loci);
}
