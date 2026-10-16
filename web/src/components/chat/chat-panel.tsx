/*
 * The chat surface, built on the owner-supplied branching-reasoning-chat-input design: rounded card,
 * scrollable transcript region, composer with send/stop, IME-safe Enter handling and a polite live region.
 * Added for this product: multi-turn transcript, per-turn direction (RTL/LTR), the real pipeline trace,
 * cited answers, the 1,000-character limit (K-07) and a demo transport when no backend is running.
 */
import * as React from "react";
import { ArrowUp, Square } from "lucide-react";

import { Answer } from "@/components/chat/answer";
import { PipelineTrace } from "@/components/ui/pipeline-trace";
import type { AssistantTurn, HistoryItem, Lang, Stage, StreamEvent } from "@/lib/api";
import { streamChat } from "@/lib/api";
import { demoChat } from "@/lib/demo";
import { detectLang, dirOf, t } from "@/lib/i18n";

const MAX_CHARS = 1000;

class BackendError extends Error {
  constructor(readonly code: string) {
    super(`backend error ${code}`);
  }
}

type Entry =
  | { kind: "user"; id: string; text: string; lang: Lang }
  | { kind: "assistant"; id: string; lang: Lang; stage: Stage | null; turn: AssistantTurn | null; error: string };

function plainText(turn: AssistantTurn): string {
  return [turn.message, ...turn.claims.map((c) => c.text)].filter(Boolean).join(" ");
}

export function ChatPanel({
  uiLang,
  resetKey,
  onDemo,
  starter,
}: {
  uiLang: Lang;
  resetKey: number;
  onDemo: (demo: boolean) => void;
  starter: string | null;
}) {
  const s = t(uiLang);
  const [entries, setEntries] = React.useState<Entry[]>([]);
  const [draft, setDraft] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [announcement, setAnnouncement] = React.useState("");
  const abort = React.useRef<AbortController | null>(null);
  const transcript = React.useRef<HTMLDivElement | null>(null);
  const demo = React.useRef(false);
  const inputId = React.useId();

  React.useEffect(() => {
    abort.current?.abort();
    setEntries([]);
    setDraft("");
    setBusy(false);
  }, [resetKey]);

  React.useEffect(() => {
    transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: "smooth" });
  }, [entries]);

  const history = (): HistoryItem[] =>
    entries.flatMap((e): HistoryItem[] =>
      e.kind === "user"
        ? [{ role: "user", text: e.text }]
        : e.turn
          ? [{ role: "assistant", text: plainText(e.turn), signature: e.turn.signature }]
          : [],
    );

  async function send(text: string) {
    const message = text.trim().slice(0, MAX_CHARS);
    if (!message || busy) return;
    const lang = detectLang(message);
    const replyId = crypto.randomUUID();
    const past = history();
    setEntries((prev) => [
      ...prev,
      { kind: "user", id: crypto.randomUUID(), text: message, lang },
      { kind: "assistant", id: replyId, lang, stage: "planning", turn: null, error: "" },
    ]);
    setDraft("");
    setBusy(true);
    const controller = new AbortController();
    abort.current = controller;
    const update = (patch: Partial<Extract<Entry, { kind: "assistant" }>>) =>
      setEntries((prev) => prev.map((e) => (e.id === replyId && e.kind === "assistant" ? { ...e, ...patch } : e)));

    const consume = async (events: AsyncGenerator<StreamEvent>) => {
      for await (const event of events) {
        if (event.type === "stage") update({ stage: event.stage });
        else if (event.type === "final") {
          update({ turn: event.turn, stage: null, lang: event.turn.lang });
          setAnnouncement(plainText(event.turn));
        } else if (event.type === "error") throw new BackendError(event.code);
      }
    };

    try {
      if (demo.current) await consume(demoChat(message, controller.signal));
      else {
        try {
          await consume(streamChat(message, past, controller.signal));
        } catch (err) {
          // No backend in development (network error, or the dev proxy's 502/503/504):
          // switch to the labelled demo transport. Never in a production build.
          const unreachable = err instanceof TypeError || (err instanceof BackendError && /^50[234]$/.test(err.code));
          if (import.meta.env.DEV && unreachable) {
            demo.current = true;
            onDemo(true);
            await consume(demoChat(message, controller.signal));
          } else throw err;
        }
      }
    } catch (err) {
      const code = err instanceof BackendError ? err.code : "";
      if ((err as Error).name === "AbortError") {
        /* the user cancelled */
      } else if (code === "400") {
        // history_invalid (ACCEPTANCE G-07): start over with only this exchange, so no unverified turn is reused.
        setEntries((prev) => prev.filter((e) => e.id === replyId || (e.kind === "user" && e.text === message)).slice(-2));
        update({ error: t(lang).historyReset, stage: null });
      } else if (code === "429") update({ error: t(lang).rateLimited, stage: null });
      else update({ error: t(lang).status.error, stage: null });
    } finally {
      setBusy(false);
      abort.current = null;
    }
  }

  React.useEffect(() => {
    if (starter) void send(starter);
    // starter changes only when the user picks an example
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [starter]);

  return (
    <div
      data-slot="chat-panel"
      className="flex h-full min-h-0 w-full flex-col rounded-md border border-border bg-card p-3 text-card-foreground sm:p-4"
    >
      <div
        ref={transcript}
        role="log"
        aria-label={s.appName}
        tabIndex={0}
        className="min-h-0 flex-1 space-y-4 overflow-y-auto overflow-x-hidden rounded-xl px-1 outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {entries.map((entry) =>
          entry.kind === "user" ? (
            <p
              key={entry.id}
              dir={dirOf(entry.lang)}
              className="ms-auto w-fit max-w-[90%] rounded-md bg-muted px-3 py-2 text-[14px] font-medium leading-6 [overflow-wrap:anywhere]"
            >
              {entry.text}
            </p>
          ) : (
            <div key={entry.id} dir={dirOf(entry.lang)} className="max-w-full">
              <PipelineTrace stage={entry.stage} trace={entry.turn?.trace ?? null} s={t(entry.lang)} />
              {entry.turn && <Answer turn={entry.turn} onOption={(o) => void send(o)} />}
              {entry.error && (
                <div className="flex items-center gap-3 rounded-xl border border-destructive/40 p-3 text-sm">
                  <span>{entry.error}</span>
                </div>
              )}
              {!entry.turn && !entry.error && (
                <span aria-hidden="true" className="ms-1 inline-block h-3 w-1 rounded-full bg-primary motion-safe:animate-pulse" />
              )}
            </div>
          ),
        )}
      </div>

      <form
        data-composer
        onSubmit={(event) => {
          event.preventDefault();
          void send(draft);
        }}
        className="mt-3 shrink-0 rounded-md border-2 border-border bg-background p-2.5 focus-within:border-primary"
      >
        <label htmlFor={inputId} className="sr-only">
          {s.yourQuestion}
        </label>
        <textarea
          id={inputId}
          value={draft}
          dir="auto"
          placeholder={s.placeholder}
          maxLength={MAX_CHARS}
          rows={2}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
              event.preventDefault();
              void send(draft);
            }
          }}
          className="block w-full resize-none rounded-lg bg-transparent px-1 py-1.5 text-[14px] leading-6 outline-none placeholder:text-muted-foreground"
        />
        <div className="flex items-center justify-between gap-3">
          <span className="ps-1 text-[11px] tabular-nums text-muted-foreground">{s.tooLong(draft.length)}</span>
          <button
            type={busy ? "button" : "submit"}
            aria-label={busy ? s.stop : s.send}
            disabled={busy ? false : !draft.trim()}
            onClick={busy ? () => abort.current?.abort() : undefined}
            className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-30"
          >
            {busy ? <Square className="size-3 fill-current" aria-hidden="true" /> : <ArrowUp className="size-4 rtl:-scale-x-100" aria-hidden="true" />}
          </button>
        </div>
      </form>
      <p role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </p>
    </div>
  );
}
