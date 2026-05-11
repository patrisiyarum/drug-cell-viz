"use client";

import Link from "next/link";
import { ArrowRight, Eye, Dna, MessageCircle } from "lucide-react";

/**
 * Landing page.
 *
 * Kintsugi visual principles:
 *   - Restrained palette (paper white + ink black) with one accent: gold.
 *   - Gold "seams" between sections — visible joins, not hidden ones.
 *   - As little text as possible while still conveying what the tool is.
 */
export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col bg-white">
      <main className="flex-1 flex flex-col">
        {/* Hero */}
        <section className="flex-1 flex items-center justify-center px-6 py-20 md:py-28">
          <div className="max-w-3xl mx-auto text-center space-y-8">
            <h1 className="text-4xl md:text-6xl leading-tight font-semibold tracking-tight">
              Built for women navigating ovarian, breast, and gynecologic cancer.
            </h1>
            <p className="text-lg text-muted-foreground max-w-xl mx-auto">
              Understand how your medications work with your genetics. Grounded in FDA
              labels and clinical guidelines for female-specific oncology.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <Link
                href="/build"
                className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-xl hover:opacity-90 transition-opacity"
              >
                Try it for yourself
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                href="/demo"
                className="inline-flex items-center gap-2 px-6 py-3 border border-border bg-white rounded-xl hover:bg-accent transition-colors text-sm"
              >
                Patient profiles
              </Link>
              <Link
                href="/screen"
                className="inline-flex items-center gap-2 px-6 py-3 border border-border bg-white rounded-xl hover:bg-accent transition-colors text-sm"
              >
                Clinical drug screening
              </Link>
            </div>
          </div>
        </section>

        {/* Kintsugi seam — the gold join between hero and features */}
        <div
          aria-hidden
          className="h-px max-w-md mx-auto bg-gradient-to-r from-transparent via-amber-500 to-transparent"
        />

        {/* Three short feature panels — minimal copy */}
        <section className="px-6 py-20">
          <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6">
            <FeaturePanel
              icon={<Eye className="w-5 h-5 text-primary" />}
              title="See your medication at work"
              body="3D protein view of where the drug binds, in plain language."
            />
            <FeaturePanel
              icon={<Dna className="w-5 h-5 text-primary" />}
              title="HRD, BRCA, and PARP inhibitors"
              body="What your BRCA variants and HR-deficiency status mean for olaparib, niraparib, and rucaparib."
            />
            <FeaturePanel
              icon={<MessageCircle className="w-5 h-5 text-primary" />}
              title="Prepared for your appointment"
              body="Specific questions to bring to your gynecologic oncologist or breast oncologist."
            />
          </div>
        </section>
      </main>

      <footer className="border-t bg-card">
        <div className="max-w-4xl mx-auto px-6 py-6 text-center">
          <p className="text-muted-foreground text-xs leading-relaxed">
            Educational. Not medical advice. Won&apos;t tell you to change a medication.
          </p>
        </div>
      </footer>
    </div>
  );
}

function FeaturePanel({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="bg-card p-6 rounded-2xl border space-y-3">
      <div
        className="w-10 h-10 rounded-lg flex items-center justify-center"
        style={{ backgroundColor: "rgba(3, 2, 19, 0.06)" }}
      >
        {icon}
      </div>
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="text-muted-foreground leading-relaxed text-sm">{body}</p>
    </div>
  );
}
