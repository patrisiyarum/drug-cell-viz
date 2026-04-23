"use client";

import { useEffect, useRef } from "react";

// Mol* has side effects on import (touches window). This whole module is only
// loaded via `next/dynamic` with ssr: false — keep it that way.
import { createPluginUI } from "molstar/lib/mol-plugin-ui";
import { renderReact18 } from "molstar/lib/mol-plugin-ui/react18";
import { DefaultPluginUISpec } from "molstar/lib/mol-plugin-ui/spec";
import type { PluginUIContext } from "molstar/lib/mol-plugin-ui/context";
import { Color } from "molstar/lib/mol-util/color";
import { setStructureOverpaint } from "molstar/lib/mol-plugin-state/helpers/structure-overpaint";
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

        // Auto-zoom to the drug (HETATM ligand) so the binding site is front
        // and center instead of showing a tiny drug inside a huge protein blob.
        await focusOnLigand(plugin);

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

async function focusOnLigand(plugin: PluginUIContext): Promise<void> {
  const structureRef = plugin.managers.structure.hierarchy.current.structures[0];
  if (!structureRef?.cell.obj) return;
  const structure = structureRef.cell.obj.data;

  // Select non-water HETATM atoms → the ligand.
  const selection = Script.getStructureSelection(
    (Q: any) =>
      Q.struct.generator.atomGroups({
        "residue-test": Q.core.logic.and([
          Q.core.rel.eq([
            Q.struct.atomProperty.macromolecular.isHet(),
            true,
          ]),
          Q.core.rel.neq([
            Q.struct.atomProperty.macromolecular.label_comp_id(),
            "HOH",
          ]),
        ]),
      }),
    structure,
  );
  const loci = StructureSelection.toLociWithSourceUnits(selection);
  if (loci.elements.length === 0) return;
  // Extra radius: show pocket walls around the drug, not just the drug alone.
  plugin.managers.camera.focusLoci(loci, { extraRadius: 8 });
}

async function highlightResidues(
  plugin: PluginUIContext,
  highlights: VariantHighlight[],
): Promise<void> {
  const structureRef = plugin.managers.structure.hierarchy.current.structures[0];
  if (!structureRef?.cell.obj) return;
  const structure = structureRef.cell.obj.data;

  const positions = highlights.map((h) => h.position);
  if (positions.length === 0) return;

  // Build a structure selection for every residue whose auth_seq_id matches
  // a variant position. Mol*'s structure-query language is the reliable way
  // to do this across chain relabelling in AlphaFold PDBs.
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

  // Bright yellow overpaint layered on top of the default cartoon coloring —
  // recolors just the variant residue(s) without touching the rest of the
  // protein. Way more visible than the cyan selection-ring default.
  const YELLOW = Color(0xf5d000);
  const components = structureRef.components ?? [];
  // setStructureOverpaint's selector callback receives a Structure and
  // returns a Loci. We re-run the same atom-groups query per structure so
  // the overpaint picks up the right atoms even when there are multiple
  // components (cartoon, ligand, etc.) sharing the underlying model.
  await setStructureOverpaint(plugin, components, YELLOW, async (s) => {
    const sel = Script.getStructureSelection(
      (Q: any) =>
        Q.struct.generator.atomGroups({
          "residue-test": Q.core.set.has([
            Q.set(...positions),
            Q.struct.atomProperty.macromolecular.auth_seq_id(),
          ]),
        }),
      s,
    );
    return StructureSelection.toLociWithSourceUnits(sel);
  });

  // Also set a persistent selection so hovering the legend highlights the
  // residue and the built-in "focus selection" button zooms to it.
  plugin.managers.structure.selection.fromLoci("set", loci);
}
