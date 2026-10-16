/*
 * One assistant turn: status, claims with citation markers, conflict callout, missing information,
 * clarify options and source cards. Everything is rendered as text (no innerHTML). Page numbers come
 * from server citations only (non-negotiable 2). Every citation marker and source card opens the
 * evidence spotlight: the real PDF page with the quote highlighted.
 */
import * as React from "react";
import { AlertTriangle, BookOpen, FileText } from "lucide-react";

import { EvidenceSpotlight } from "@/components/chat/evidence-spotlight";
import { SectionHeading } from "@/components/ui/section-heading";
import type { AssistantTurn, Citation, Claim, Lang } from "@/lib/api";
import { dirOf, t } from "@/lib/i18n";

type Open = (n: number, trigger: HTMLElement) => void;

function Marker({ n, lang, onOpen }: { n: number; lang: Lang; onOpen: Open }) {
  return (
    <button
      type="button"
      onClick={(e) => onOpen(n, e.currentTarget)}
      className="mx-0.5 inline-flex h-4 min-w-4 cursor-pointer items-center justify-center rounded bg-primary px-1 align-super text-[10px] font-semibold text-primary-foreground outline-none transition-transform hover:scale-110 hover:bg-primary/85 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
      aria-label={t(lang).spotlight.open(n)}
      aria-haspopup="dialog"
    >
      {n}
    </button>
  );
}

function ClaimLine({ claim, lang, onOpen }: { claim: Claim; lang: Lang; onOpen: Open }) {
  return (
    <p className="leading-7 [overflow-wrap:anywhere]">
      <span style={{ unicodeBidi: "plaintext" }}>{claim.text}</span>
      {claim.citations.map((n) => (
        <Marker key={n} n={n} lang={lang} onOpen={onOpen} />
      ))}
    </p>
  );
}

function SourceCard({ c, turnId, lang, onOpen }: { c: Citation; turnId: string; lang: Lang; onOpen: Open }) {
  const s = t(lang);
  const page = s.pdfPage(c.pdfPage) + (c.printedLabel && c.printedLabel !== String(c.pdfPage) ? ` · ${s.printedPage(c.printedLabel)}` : "");
  return (
    <li id={`src-${turnId}-${c.n}`} className="scroll-mt-24 rounded-md bg-muted p-3 text-sm">
      <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex size-5 items-center justify-center rounded bg-primary text-[10px] font-semibold text-primary-foreground">
          {c.n}
        </span>
        <FileText className="size-3.5" aria-hidden="true" />
        <bdi className="font-bold text-foreground">{c.docSubtitle}</bdi>
        <span>·</span>
        <span>{page}</span>
        <span>·</span>
        <bdi>{c.section}</bdi>
      </div>
      <blockquote dir="ltr" lang="en" className="border-s-2 border-primary/50 ps-3 text-[13px] leading-6 text-foreground/90">
        “{c.quote}”
      </blockquote>
      <button
        type="button"
        onClick={(e) => onOpen(c.n, e.currentTarget)}
        aria-haspopup="dialog"
        aria-label={s.spotlight.open(c.n)}
        className="mt-2 inline-flex cursor-pointer items-center gap-1 text-xs font-medium text-primary hover:underline dark:text-accent-foreground focus-visible:outline-2 focus-visible:outline-ring"
      >
        <BookOpen className="size-3.5" aria-hidden="true" />
        {s.viewSource}
      </button>
    </li>
  );
}

export function Answer({ turn, onOption }: { turn: AssistantTurn; onOption: (text: string) => void }) {
  const s = t(turn.lang);
  const badge = s.status[turn.status];
  // Claims shown as a side of a reported conflict appear only in that conflict's callout.
  const inConflict = new Set(turn.conflicts.flatMap((c) => c.positions.map((p) => p.text)));
  const body = turn.claims.filter((c) => !(c.kind === "conflict_position" && inConflict.has(c.text)));
  const [spotlight, setSpotlight] = React.useState<{ citation: Citation; trigger: HTMLElement } | null>(null);
  const open: Open = (n, trigger) => {
    const citation = turn.citations.find((c) => c.n === n);
    if (citation) setSpotlight({ citation, trigger });
  };
  return (
    <div dir={dirOf(turn.lang)} lang={turn.lang} className="space-y-3 text-[14px]">
      {(badge || turn.flags.length > 0) && (
        <div className="flex flex-wrap gap-1.5">
          {badge && turn.status !== "answered" && (
            <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
              {badge}
            </span>
          )}
          {turn.flags.map((f) => (
            <span
              key={f}
              className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                f === "conflict" ? "bg-warning text-warning-foreground" : "bg-accent text-accent-foreground"
              }`}
            >
              {s.flag[f]}
            </span>
          ))}
        </div>
      )}

      {turn.message && <p className="leading-7">{turn.message}</p>}
      {body.map((claim, i) => (
        <ClaimLine key={i} claim={claim} lang={turn.lang} onOpen={open} />
      ))}

      {turn.conflicts.map((conflict, i) => (
        <section key={i} role="note" className="rounded-md border-s-4 border-brand-amber bg-warning p-3 text-warning-foreground">
          <h3 className="mb-1 flex items-center gap-1.5 text-sm font-semibold">
            <AlertTriangle className="size-4" aria-hidden="true" />
            {s.conflictTitle} — <bdi>{conflict.topic}</bdi>
          </h3>
          <p className="mb-2 text-xs opacity-80">{s.conflictNote}</p>
          <ul className="space-y-1.5">
            {conflict.positions.map((position, j) => (
              <li key={j} className="text-[13px] text-foreground">
                <ClaimLine
                  claim={{ text: position.text, kind: "conflict_position", citations: position.citations }}
                  lang={turn.lang}
                  onOpen={open}
                />
              </li>
            ))}
          </ul>
        </section>
      ))}

      {turn.missing.length > 0 && (
        <section className="rounded-md bg-muted p-3">
          <h3 className="mb-1 text-sm font-semibold">{s.missingTitle}</h3>
          <ul className="list-disc space-y-1 ps-5 text-[13px]">
            {turn.missing.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </section>
      )}

      {turn.clarify && (
        <div className="space-y-2">
          <p className="font-medium">{turn.clarify.question}</p>
          <div className="flex flex-wrap gap-2">
            {turn.clarify.options.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onOption(option)}
                className="rounded-full border border-primary/40 px-3 py-1 text-xs font-medium text-primary hover:bg-accent dark:text-accent-foreground focus-visible:outline-2 focus-visible:outline-ring"
              >
                {option}
              </button>
            ))}
          </div>
        </div>
      )}

      {turn.citations.length > 0 && (
        <section aria-label={s.sources}>
          <div className="mb-2"><SectionHeading as="h3">{s.sources}</SectionHeading></div>
          <ol className="space-y-2">
            {turn.citations.map((c) => (
              <SourceCard key={c.n} c={c} turnId={turn.id} lang={turn.lang} onOpen={open} />
            ))}
          </ol>
        </section>
      )}

      <EvidenceSpotlight
        citation={spotlight?.citation ?? null}
        returnFocus={spotlight?.trigger}
        lang={turn.lang}
        onClose={() => setSpotlight(null)}
      />
    </div>
  );
}
