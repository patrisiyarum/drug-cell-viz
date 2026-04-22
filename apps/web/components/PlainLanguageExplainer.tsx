"use client";

import { useState } from "react";
import type { GlossaryTerm, PlainLanguage } from "@/lib/bc-types";

interface Props {
  plain: PlainLanguage;
}

export function PlainLanguageExplainer({ plain }: Props) {
  return (
    <div className="space-y-3">
      <Block
        title="What you're looking at"
        icon="🔬"
        body={plain.what_you_see}
        accent="bg-blue-50 border-blue-200"
      />
      <Block
        title="How this drug works"
        icon="💊"
        body={plain.how_the_drug_works}
        accent="bg-purple-50 border-purple-200"
      />
      <Block
        title="What this means for you"
        icon="🧬"
        body={plain.what_it_means_for_you}
        accent="bg-amber-50 border-amber-200"
      />
      <Block
        title="Next steps"
        icon="👉"
        body={plain.next_steps}
        accent="bg-slate-50 border-slate-200"
      />
      <Glossary items={plain.glossary} />
    </div>
  );
}

function Block({
  title,
  icon,
  body,
  accent,
}: {
  title: string;
  icon: string;
  body: string;
  accent: string;
}) {
  return (
    <section className={`border rounded px-4 py-3 ${accent}`}>
      <div className="text-sm font-semibold flex items-center gap-2">
        <span aria-hidden className="text-lg">
          {icon}
        </span>
        <span>{title}</span>
      </div>
      <p className="text-sm text-gray-800 mt-1 leading-relaxed">{body}</p>
    </section>
  );
}

function Glossary({ items }: { items: GlossaryTerm[] }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <section className="border rounded bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full text-left px-4 py-2 text-sm font-medium flex items-center justify-between"
      >
        <span>📖 Words used on this page, explained ({items.length})</span>
        <span className="text-gray-400 text-xs">{open ? "hide" : "show"}</span>
      </button>
      {open ? (
        <dl className="border-t px-4 py-3 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 text-sm">
          {items.map((g) => (
            <div key={g.term} className="flex flex-col">
              <dt className="font-semibold">{g.term}</dt>
              <dd className="text-gray-700">{g.definition}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  );
}
