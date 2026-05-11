"use client";

import { useEffect, useRef, useState } from "react";
import { MessageCircle, Send, X } from "lucide-react";

import { api } from "@/lib/api";
import type { AnalysisResult, DemoPatient } from "@/lib/bc-types";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: { url: string; title: string }[];
}

interface Props {
  result: AnalysisResult;
  patient?: DemoPatient | null;
  /** User-entered cancer type. Falls back to patient.indication when present. */
  indication?: string | null;
  /** Display label for the patient ("Anna" / "Maya") used in the welcome message. */
  patientLabel?: string | null;
}

/**
 * Conversational walkthrough that explains the analysis results in
 * plain English and answers follow-up questions. Posts to
 * /api/agent/walkthrough on every turn with the full message history
 * plus the structured analysis context.
 *
 * The chat starts collapsed as a floating button and expands into a
 * side drawer so it doesn't fight the two-card results layout for
 * vertical space. State (messages, open/closed) is local — the chat
 * resets if the analysis result changes.
 */
export function WalkthroughChat({
  result,
  patient,
  indication,
  patientLabel,
}: Props) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const scrollerRef = useRef<HTMLDivElement | null>(null);

  // Reset the conversation whenever a new analysis lands so the agent
  // isn't reasoning over stale context.
  useEffect(() => {
    setMessages([]);
    setInput("");
    setErr(null);
  }, [result.id]);

  // Auto-scroll to the latest message.
  useEffect(() => {
    if (scrollerRef.current) {
      scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
    }
  }, [messages, pending]);

  const effectiveIndication = indication ?? patient?.indication ?? null;
  const name = patientLabel ?? patient?.persona_name ?? null;

  const context = buildContext(result, effectiveIndication, name);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    const next: ChatMessage[] = [
      ...messages,
      { role: "user", content: trimmed },
    ];
    setMessages(next);
    setInput("");
    setPending(true);
    setErr(null);
    try {
      const resp = await api.walkthroughChat(
        next.map((m) => ({ role: m.role, content: m.content })),
        context,
      );
      setMessages([
        ...next,
        {
          role: "assistant",
          content: resp.reply,
          citations: resp.citations,
        },
      ]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Chat failed");
    } finally {
      setPending(false);
    }
  }

  function startConversation() {
    if (messages.length === 0 && !pending) {
      void send(
        effectiveIndication
          ? `I have ${effectiveIndication}. Walk me through what these results mean for me, and what I should ask my oncologist.`
          : "Walk me through what these results mean and what I should ask my oncologist.",
      );
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setOpen(true);
          // Defer kickoff so the drawer is mounted when the response lands.
          setTimeout(startConversation, 50);
        }}
        className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-full bg-primary text-primary-foreground px-5 py-3 shadow-lg hover:opacity-90 transition-opacity no-print"
        aria-label="Open walkthrough chat"
      >
        <MessageCircle className="w-5 h-5" aria-hidden />
        <span className="text-sm font-medium">Talk through my results</span>
      </button>
    );
  }

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-full sm:w-[420px] bg-white border-l shadow-xl flex flex-col no-print">
      <header className="flex items-center justify-between gap-2 p-4 border-b">
        <div>
          <div className="text-sm font-semibold">Talk through your results</div>
          <div className="text-[11px] text-muted-foreground">
            Powered by Claude · can search the web for current sources
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="p-1.5 rounded-md hover:bg-muted"
          aria-label="Close chat"
        >
          <X className="w-4 h-4" aria-hidden />
        </button>
      </header>

      <div
        ref={scrollerRef}
        className="flex-1 overflow-y-auto p-4 space-y-4"
      >
        {messages.length === 0 && !pending ? (
          <div className="text-sm text-muted-foreground space-y-3">
            <p>
              I&apos;ll walk you through what this analysis means for your
              cancer in plain English. Ask me anything — I can also look up
              current information on the web.
            </p>
            <button
              type="button"
              onClick={startConversation}
              className="text-sm rounded-lg border bg-amber-50 hover:bg-amber-100 border-amber-300 px-3 py-2"
            >
              Walk me through this
            </button>
          </div>
        ) : null}

        {messages.map((m, i) => (
          <ChatBubble key={i} msg={m} />
        ))}
        {pending ? (
          <div className="text-xs text-muted-foreground italic">Thinking…</div>
        ) : null}
        {err ? <p className="text-xs text-red-600">{err}</p> : null}
      </div>

      <footer className="border-t p-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
          className="flex items-end gap-2"
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(input);
              }
            }}
            rows={2}
            placeholder="Ask a follow-up — e.g. 'what does HRD mean for my treatment?'"
            className="flex-1 rounded-lg border px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/30"
            disabled={pending}
          />
          <button
            type="submit"
            disabled={pending || !input.trim()}
            className="rounded-lg bg-primary text-primary-foreground p-2 disabled:opacity-50"
            aria-label="Send"
          >
            <Send className="w-4 h-4" aria-hidden />
          </button>
        </form>
        <p className="mt-2 text-[10px] text-muted-foreground leading-snug">
          Educational only. Not medical advice. Always discuss treatment
          decisions with your oncologist.
        </p>
      </footer>
    </div>
  );
}

function ChatBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        }`}
      >
        {msg.content}
        {msg.citations && msg.citations.length > 0 ? (
          <div className="mt-2 pt-2 border-t border-current/10 space-y-1">
            <div className="text-[10px] uppercase tracking-wide opacity-70">
              Sources
            </div>
            {msg.citations.map((c) => (
              <a
                key={c.url}
                href={c.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block text-[11px] underline opacity-90 hover:opacity-100 truncate"
              >
                {c.title || c.url}
              </a>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Pull the analysis context Claude needs into a JSON-friendly object.
 * We deliberately drop heavy/unstructured fields (e.g. raw PDB blobs)
 * and keep the things that matter for explaining results: the verdict,
 * the variants, the suggested drugs, and the patient's cancer type.
 */
function buildContext(
  result: AnalysisResult,
  indication: string | null,
  name: string | null,
): Record<string, unknown> {
  return {
    patient_name: name,
    cancer_type: indication,
    drug: {
      id: result.drug_id,
      name: result.drug_name,
      target_gene: result.target_gene,
    },
    hrd: result.hrd
      ? {
          label: result.hrd.label,
          score: result.hrd.score,
          evidence: result.hrd.evidence,
        }
      : null,
    classifiable_brca1_variants: result.classifiable_brca1_variants ?? [],
    suggested_drugs: result.suggested_drugs ?? [],
    relevance_warning: result.relevance_warning ?? null,
    off_target_genes: (result.off_target_structures ?? []).map(
      (s) => s.gene_symbol,
    ),
  };
}
