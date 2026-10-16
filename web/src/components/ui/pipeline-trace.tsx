"use client";

/*
 * pipeline-trace: replaces the "approaches with scores" deck of the owner-supplied
 * branching-reasoning-chat-input with the REAL answering pipeline (ADR-0001 D23), drawn as
 * almamlakatv.com's red dot-and-line timeline: understand the question, search the documents,
 * verify every claim. All numbers come from the server's trace; nothing is invented.
 */

import * as React from "react";
import { ChevronDown } from "lucide-react";

import type { Stage, Trace } from "@/lib/api";
import type { Strings } from "@/lib/i18n";

const ORDER: Stage[] = ["planning", "retrieving", "answering", "verifying"];

export function PipelineTrace({ stage, trace, s }: { stage: Stage | null; trace: Trace | null; s: Strings }) {
  const [open, setOpen] = React.useState(false);
  const listId = React.useId();
  const running = trace === null;
  const reached = stage ? ORDER.indexOf(stage) : -1;

  const steps = [
    {
      title: s.traceCards.understand,
      note: trace ? s.traceCards.queries(trace.searches.length) : s.stage.planning,
      done: !running || reached > 0,
      current: running && reached === 0,
    },
    {
      title: s.traceCards.search(trace?.documentsSearched.length ?? 3),
      note: trace ? (trace.denseFallback ? s.traceCards.fallback : s.traceCards.passages(trace.retrieved.length)) : s.stage.retrieving,
      done: !running || reached > 1,
      current: running && reached === 1,
    },
    {
      title: s.traceCards.verify,
      note: trace ? s.traceCards.verified(trace.claimsVerified, trace.claimsRemoved) : s.stage.verifying,
      done: !running,
      current: running && reached >= 2,
    },
  ];
  const expanded = running || open;

  return (
    <div data-slot="pipeline-trace" className="mb-3">
      {running ? (
        <p role="status" aria-live="polite" className="sr-only">
          {stage ? s.stage[stage] : ""}
        </p>
      ) : (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 text-xs font-bold text-muted-foreground hover:text-primary focus-visible:outline-2 focus-visible:outline-ring"
        >
          {s.howAnswered}
          <ChevronDown className={`size-3 transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`} aria-hidden="true" />
        </button>
      )}
      {expanded && (
        <ol id={listId} className="relative mt-2 grid grid-cols-3 gap-2">
          {/* the red line behind the dots */}
          <span aria-hidden="true" className="absolute inset-x-[16%] top-[7px] h-0.5 bg-primary/25" />
          {steps.map((step) => (
            <li key={step.title} className="relative flex flex-col items-center text-center">
              <span
                aria-hidden="true"
                className={`z-10 size-4 rounded-full border-2 border-primary ${
                  step.done ? "bg-primary" : step.current ? "bg-background motion-safe:animate-pulse" : "bg-background"
                }`}
              />
              <span className={`mt-1.5 text-[12px] font-bold leading-tight ${step.done || step.current ? "" : "text-muted-foreground"}`}>
                {step.title}
              </span>
              <span className="mt-0.5 text-[11px] leading-tight text-muted-foreground">{step.note}</span>
            </li>
          ))}
        </ol>
      )}
      {!running && open && trace && (
        <p className="mt-2 text-[11px] leading-5 text-muted-foreground" dir="ltr">
          <bdi>{trace.retrieved.join(" · ")}</bdi>
        </p>
      )}
    </div>
  );
}

export default PipelineTrace;
