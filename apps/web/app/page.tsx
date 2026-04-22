"use client";

import Link from "next/link";
import { ArrowRight, Eye, Dna, MessageCircle } from "lucide-react";

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col relative overflow-hidden bg-white">
      {/* Decorative organic shapes — kept subtle so the page feels calm. */}
      <div aria-hidden className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full blur-3xl"
             style={{ background: "radial-gradient(closest-side, rgba(37,99,235,0.06), transparent)" }} />
        <div className="absolute top-1/2 -left-32 w-80 h-80 rounded-full blur-3xl"
             style={{ background: "radial-gradient(closest-side, rgba(217,119,6,0.06), transparent)" }} />
        <div className="absolute -bottom-32 right-1/4 w-96 h-96 rounded-full blur-3xl"
             style={{ background: "radial-gradient(closest-side, rgba(22,163,74,0.06), transparent)" }} />
      </div>

      <main className="flex-1 flex flex-col relative z-10">
        <section className="flex-1 flex items-center justify-center px-6 md:px-8 py-20 md:py-28">
          <div className="max-w-4xl mx-auto text-center space-y-8">
            <h1 className="text-4xl md:text-6xl max-w-3xl mx-auto leading-tight font-semibold tracking-tight">
              Understand how your medications work with your body.
            </h1>
            <p className="text-lg md:text-xl max-w-2xl mx-auto text-muted-foreground">
              A tool for people living with cancer who want to be informed about their treatment.
              Based on FDA and clinical guidelines.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <Link
                href="/build"
                className="inline-flex items-center gap-2 px-7 py-4 bg-primary text-primary-foreground rounded-xl hover:opacity-90 transition-opacity"
              >
                Try it for yourself
                <ArrowRight className="w-5 h-5" />
              </Link>
              <Link
                href="/demo"
                className="inline-flex items-center gap-2 px-7 py-4 border border-border bg-white rounded-xl hover:bg-accent transition-colors text-sm"
              >
                See how it works
              </Link>
              <Link
                href="/screen"
                className="inline-flex items-center gap-2 px-7 py-4 border border-border bg-white rounded-xl hover:bg-accent transition-colors text-sm"
              >
                Virtual screening (experimental)
              </Link>
            </div>
          </div>
        </section>

        <section className="px-6 md:px-8 pb-24">
          <div className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-10">
            <FeaturePanel
              icon={<Eye className="w-6 h-6 text-primary" />}
              title="See your medication at work"
              body="Visualize in 3D how drugs interact with proteins in your body, explained in plain language."
            />
            <FeaturePanel
              icon={<Dna className="w-6 h-6 text-primary" />}
              title="Understand your genetics"
              body="Learn how genetic variants affect drug processing, without the technical jargon."
            />
            <FeaturePanel
              icon={<MessageCircle className="w-6 h-6 text-primary" />}
              title="Walk into appointments prepared"
              body="Get specific questions to ask your care team about your treatment options."
            />
          </div>
        </section>
      </main>

      <footer className="border-t bg-card">
        <div className="max-w-6xl mx-auto px-8 py-8 text-center">
          <p className="text-muted-foreground leading-relaxed max-w-3xl mx-auto text-sm">
            For education and better conversations with your care team. Not a substitute for
            medical advice. Will never tell you to change a medication.
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
    <div className="bg-card p-8 md:p-10 rounded-2xl border space-y-4">
      <div
        className="w-12 h-12 rounded-xl flex items-center justify-center"
        style={{ backgroundColor: "rgba(3, 2, 19, 0.06)" }}
      >
        {icon}
      </div>
      <h3 className="text-xl md:text-2xl font-semibold">{title}</h3>
      <p className="text-muted-foreground leading-relaxed text-sm md:text-base">{body}</p>
    </div>
  );
}
