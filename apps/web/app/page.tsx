"use client";

import Link from "next/link";
import { ArrowRight, Eye, Dna, MessageCircle, Sparkles } from "lucide-react";

/**
 * Landing page.
 *
 * Visual direction: a warm paper palette — base white + ink black with
 * dusty rose and amber as accents, layered as soft gradients so the
 * page feels considered rather than clinical. The "kintsugi seam" idea
 * is retained but rendered as a thicker, more deliberate gold join
 * across the page rather than a thin line buried between sections.
 */
export default function LandingPage() {
  return (
    <div
      className="min-h-screen flex flex-col relative overflow-hidden"
      style={{
        background:
          "radial-gradient(ellipse 90% 60% at 50% 0%, #fff7ed 0%, #ffffff 45%, #fdf2f8 100%)",
      }}
    >
      {/* Decorative soft blobs anchored top-left + bottom-right so the
          background reads as layered warm light rather than a flat
          gradient. Pointer-events-none so they don't fight clicks. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-32 -left-32 w-[36rem] h-[36rem] rounded-full opacity-60 blur-3xl"
        style={{
          background: "radial-gradient(circle, #fde68a 0%, transparent 65%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-40 -right-32 w-[34rem] h-[34rem] rounded-full opacity-50 blur-3xl"
        style={{
          background: "radial-gradient(circle, #fbcfe8 0%, transparent 65%)",
        }}
      />

      <main className="flex-1 flex flex-col relative z-10">
        {/* Hero */}
        <section className="flex-1 flex items-center justify-center px-6 py-20 md:py-28">
          <div className="max-w-3xl mx-auto text-center space-y-8">
            <span className="inline-flex items-center gap-2 rounded-full border border-amber-200 bg-white/70 backdrop-blur-sm px-3 py-1 text-xs font-medium tracking-wide text-amber-800 shadow-sm">
              <Sparkles className="w-3 h-3" aria-hidden />
              For women navigating cancer treatment
            </span>
            <h1 className="text-4xl md:text-6xl leading-[1.1] font-semibold tracking-tight">
              Turn your diagnosis into{" "}
              <span
                className="bg-clip-text text-transparent"
                style={{
                  backgroundImage:
                    "linear-gradient(120deg, #b45309 0%, #ea580c 35%, #be185d 100%)",
                }}
              >
                a plan you can act on
              </span>
              .
            </h1>
            <p className="text-base md:text-lg text-muted-foreground max-w-xl mx-auto leading-relaxed">
              See how your medications work with your genetics. Walk into
              your next appointment with the questions that matter most.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
              <Link
                href="/build"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-white shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5"
                style={{
                  backgroundImage:
                    "linear-gradient(135deg, #ea580c 0%, #be185d 100%)",
                }}
              >
                Try it for yourself
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                href="/demo"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-amber-200 bg-white/80 backdrop-blur-sm hover:bg-white transition-colors text-sm font-medium"
              >
                Patient profiles
              </Link>
              <Link
                href="/screen"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-amber-200 bg-white/80 backdrop-blur-sm hover:bg-white transition-colors text-sm font-medium"
              >
                Clinical drug screening
              </Link>
            </div>
          </div>
        </section>

        {/* Kintsugi seam — slightly thicker so it reads as an intentional
            join across the page rather than a thin line you have to look
            for. */}
        <div className="relative px-6">
          <div
            aria-hidden
            className="h-[2px] max-w-2xl mx-auto rounded-full"
            style={{
              backgroundImage:
                "linear-gradient(90deg, transparent 0%, #f59e0b 30%, #ec4899 70%, transparent 100%)",
            }}
          />
        </div>

        {/* Feature panels — each gets a warm tint so the row reads as a
            row of cards, not a wall of white. */}
        <section className="px-6 py-20">
          <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6">
            <FeaturePanel
              icon={<Eye className="w-5 h-5" />}
              iconBg="from-amber-100 to-amber-200/60"
              iconColor="text-amber-700"
              title="See your medication at work"
              body="3D protein view of where the drug binds — in plain language."
            />
            <FeaturePanel
              icon={<Dna className="w-5 h-5" />}
              iconBg="from-rose-100 to-rose-200/60"
              iconColor="text-rose-700"
              title="HRD, BRCA, and PARP inhibitors"
              body="What your BRCA variants and HR-deficiency status mean for olaparib, niraparib, and rucaparib."
            />
            <FeaturePanel
              icon={<MessageCircle className="w-5 h-5" />}
              iconBg="from-pink-100 to-amber-100"
              iconColor="text-pink-700"
              title="Prepared for your appointment"
              body="Specific questions to bring to your gynecologic or breast oncologist."
            />
          </div>
        </section>
      </main>

      <footer className="border-t border-amber-100/60 bg-white/40 backdrop-blur-sm relative z-10">
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
  iconBg,
  iconColor,
  title,
  body,
}: {
  icon: React.ReactNode;
  iconBg: string;
  iconColor: string;
  title: string;
  body: string;
}) {
  return (
    <div className="group bg-white/70 backdrop-blur-sm p-6 rounded-2xl border border-amber-100/80 space-y-3 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all">
      <div
        className={`w-11 h-11 rounded-xl flex items-center justify-center bg-gradient-to-br ${iconBg} ${iconColor} shadow-sm`}
      >
        {icon}
      </div>
      <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
      <p className="text-muted-foreground leading-relaxed text-sm">{body}</p>
    </div>
  );
}
