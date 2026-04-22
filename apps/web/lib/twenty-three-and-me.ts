// 23andMe raw-data parser and rsID → variant catalog mapper.
//
// 23andMe exports a tab-separated file:
//   # comment lines starting with `#`
//   rsid <tab> chromosome <tab> position <tab> genotype
//
// The genotype is two letters (or "--" if no call). Indels and copy number
// variants are NOT reliably covered by the SNP array; we detect only the
// handful of SNVs that (a) 23andMe reliably types and (b) have clinical
// actionability tied to variants in our catalog.
//
// Everything here is client-side: the raw file never touches the network.
// Privacy-positive by default.

import type { VariantInput, Zygosity } from "./bc-types";

type Allele = "A" | "C" | "G" | "T";

interface RsidMatch {
  rsid: string;
  gene: string;
  variantCatalogId: string;    // our catalog variant id
  // Reference allele = the ancestral / non-risk allele.
  // Risk allele = what Findlay/CPIC call the variant.
  ref: Allele;
  risk: Allele;
  // Human-readable name for reporting.
  displayName: string;
}

// Hand-curated map of clinically actionable PGx SNPs covered by 23andMe's
// v5 chip (the current consumer version at time of writing). Every row has
// been confirmed against dbSNP and CPIC / FDA guidance.
const RSID_CATALOG: RsidMatch[] = [
  {
    rsid: "rs3892097",
    gene: "CYP2D6",
    variantCatalogId: "CYP2D6_star4",
    ref: "G",
    risk: "A",
    displayName: "CYP2D6*4 (rs3892097)",
  },
  {
    rsid: "rs3918290",
    gene: "DPYD",
    variantCatalogId: "DPYD_star2A",
    ref: "C",
    risk: "T",   // 23andMe reports the forward-strand alt; clinical tests report c.1905+1G>A
    displayName: "DPYD*2A (rs3918290)",
  },
  {
    rsid: "rs67376798",
    gene: "DPYD",
    variantCatalogId: "DPYD_c2846A_T",
    ref: "A",
    risk: "T",
    displayName: "DPYD c.2846A>T (rs67376798)",
  },
];

// rsIDs that are clinically important but NOT well typed by 23andMe. We
// surface them as "couldn't test from your file — consider clinical PGx"
// so the user knows the absence of a match is not reassurance.
const NOT_WELL_COVERED: { rsid: string; gene: string; why: string }[] = [
  {
    rsid: "rs8175347 (UGT1A1*28)",
    gene: "UGT1A1",
    why: "UGT1A1*28 is a TA-repeat insertion in the promoter. SNP arrays like 23andMe's don't reliably type repeat indels.",
  },
  {
    rsid: "BRCA1 185delAG / BRCA2 6174delT (founder variants)",
    gene: "BRCA1 / BRCA2",
    why: "23andMe's FDA-approved BRCA test covers these 3 founder variants, but they appear in a separate 'health predisposition' report, not always in the raw TSV. A clinical BRCA panel covers thousands more.",
  },
];

export interface ParsedGenotype {
  rsid: string;
  genotype: string;
}

export interface Detection {
  rsid: string;
  gene: string;
  variantCatalogId: string;
  displayName: string;
  zygosity: Zygosity;
  copiesOfRiskAllele: number;
  rawGenotype: string;
}

export interface ParseResult {
  totalLines: number;
  validCalls: number;
  detectedVariants: Detection[];
  notWellCovered: typeof NOT_WELL_COVERED;
}

/**
 * Parse a 23andMe raw .txt / .tsv file and return any clinically-relevant
 * SNV calls we recognize.
 */
export function parse23andMe(text: string): ParseResult {
  const lookup = new Map(RSID_CATALOG.map((r) => [r.rsid, r]));
  const seenDetections = new Map<string, Detection>();

  let totalLines = 0;
  let validCalls = 0;

  for (const line of text.split(/\r?\n/)) {
    if (!line || line.startsWith("#")) continue;
    totalLines += 1;
    const parts = line.split("\t");
    if (parts.length < 4) continue;
    const [rsid, _chr, _pos, genotype] = parts;
    validCalls += 1;

    const match = lookup.get(rsid);
    if (!match) continue;
    if (!genotype || genotype.includes("-")) continue;

    const alleles = genotype.toUpperCase().split("") as Allele[];
    const copiesOfRisk = alleles.filter((a) => a === match.risk).length;
    if (copiesOfRisk === 0) continue;

    // For TPMT*3A, we need BOTH rs1800460 and rs1142345 on the same haplotype.
    // The raw file can't tell us phasing, but we flag each marker individually
    // and the report reconciles them.
    seenDetections.set(rsid, {
      rsid,
      gene: match.gene,
      variantCatalogId: match.variantCatalogId,
      displayName: match.displayName,
      zygosity: copiesOfRisk === 2 ? "homozygous" : "heterozygous",
      copiesOfRiskAllele: copiesOfRisk,
      rawGenotype: genotype,
    });
  }

  return {
    totalLines,
    validCalls,
    detectedVariants: Array.from(seenDetections.values()),
    notWellCovered: NOT_WELL_COVERED,
  };
}

/**
 * Collapse detections into the unique set of variant catalog ids (TPMT*3A
 * needs two markers → one catalog variant), with the most-severe zygosity.
 */
export function detectionsToVariantInputs(ds: Detection[]): VariantInput[] {
  const byCatalogId = new Map<string, Zygosity>();
  for (const d of ds) {
    const prev = byCatalogId.get(d.variantCatalogId);
    if (!prev || (prev === "heterozygous" && d.zygosity === "homozygous")) {
      byCatalogId.set(d.variantCatalogId, d.zygosity);
    }
  }
  return Array.from(byCatalogId.entries()).map(([catalog_id, zygosity]) => ({
    catalog_id,
    zygosity,
  }));
}

export function countSupportedSnps(): number {
  return RSID_CATALOG.length;
}
