/*
 * Evidence spotlight (PROJECT_PLAN §5.3): a side panel showing the real PDF page with the cited quote
 * highlighted, then the document, PDF page, section and the verbatim quote. The page image and the
 * highlight boxes come from the server (app/sources_api.py), built from the index only; the boxes are
 * placed in % of the image so they scale with it. Radix Dialog gives the focus trap, Escape to close and
 * focus return to the citation that opened it. Everything is rendered as text (no innerHTML).
 */
import * as React from "react";
import { Dialog } from "radix-ui";
import { AlertTriangle, FileText, Loader2, RotateCcw, X, ZoomIn, ZoomOut } from "lucide-react";

import type { Citation, Lang, Spotlight } from "@/lib/api";
import { fetchSpotlight } from "@/lib/api";
import { dirOf, t } from "@/lib/i18n";

type Load = { state: "loading" } | { state: "error" } | { state: "ready"; data: Spotlight };

const pct = (value: number, total: number) => `${(value / total) * 100}%`;

function PageImage({ data, alt, zoom }: { data: Spotlight; alt: string; zoom: boolean }) {
  const first = React.useRef<HTMLSpanElement | null>(null);
  const [loaded, setLoaded] = React.useState(false);

  React.useEffect(() => {
    if (!loaded) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    first.current?.scrollIntoView({ block: "center", inline: "center", behavior: reduce ? "auto" : "smooth" });
  }, [loaded, zoom]);

  return (
    // Page coordinates are physical (left/top), so the page keeps LTR geometry inside an RTL panel.
    <div dir="ltr" className="overflow-x-auto rounded-md border border-border bg-white shadow-sm">
      <div className="relative" style={{ width: zoom ? "200%" : "100%" }}>
        <img
          src={data.imageUrl}
          alt={alt}
          width={data.width}
          height={data.height}
          onLoad={() => setLoaded(true)}
          className="block h-auto w-full select-none"
          draggable={false}
        />
        {data.boxes.map((b, i) => (
          <span
            key={i}
            ref={i === 0 ? first : undefined}
            aria-hidden="true"
            className="pointer-events-none absolute scroll-my-24 rounded-[3px] bg-brand-red/20 outline-2 outline-brand-red mix-blend-multiply motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-500"
            style={{
              left: pct(b.x, data.width),
              top: pct(b.y, data.height),
              width: pct(b.w, data.width),
              height: pct(b.h, data.height),
            }}
          />
        ))}
      </div>
    </div>
  );
}

export function EvidenceSpotlight({
  citation,
  lang,
  onClose,
  returnFocus,
}: {
  citation: Citation | null;
  lang: Lang;
  onClose: () => void;
  /** The control that opened the panel; focus goes back to it on close (there is no Dialog.Trigger). */
  returnFocus?: HTMLElement | null;
}) {
  const s = t(lang);
  const sp = s.spotlight;
  // Keep showing the last citation while the panel animates closed.
  const last = React.useRef<Citation | null>(citation);
  if (citation) last.current = citation;
  const shown = citation ?? last.current;
  const trigger = React.useRef<HTMLElement | null>(null);
  if (returnFocus) trigger.current = returnFocus;
  const [load, setLoad] = React.useState<Load>({ state: "loading" });
  const [attempt, setAttempt] = React.useState(0);
  const [zoom, setZoom] = React.useState(false);

  React.useEffect(() => {
    if (!citation) return;
    const controller = new AbortController();
    setLoad({ state: "loading" });
    setZoom(false);
    fetchSpotlight(citation, controller.signal).then(
      (data) => setLoad({ state: "ready", data }),
      () => {
        if (!controller.signal.aborted) setLoad({ state: "error" });
      },
    );
    return () => controller.abort();
  }, [citation, attempt]);

  const page =
    shown &&
    s.pdfPage(shown.pdfPage) +
      (shown.printedLabel && shown.printedLabel !== String(shown.pdfPage)
        ? ` · ${s.printedPage(shown.printedLabel)}`
        : "");

  return (
    <Dialog.Root open={citation !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-brand-navy/50 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0" />
        <Dialog.Content
          dir={dirOf(lang)}
          lang={lang}
          onCloseAutoFocus={(event) => {
            if (trigger.current?.isConnected) {
              event.preventDefault();
              trigger.current.focus();
            }
          }}
          className="fixed inset-y-0 end-0 z-50 flex w-full max-w-2xl flex-col border-s-4 border-primary bg-background text-foreground shadow-2xl outline-none data-[state=open]:animate-in data-[state=open]:slide-in-from-end data-[state=closed]:animate-out data-[state=closed]:slide-out-to-end"
        >
          <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
            <div className="min-w-0">
              <Dialog.Title className="flex items-center gap-2 text-base font-bold">
                {shown && (
                  <span className="inline-flex size-6 items-center justify-center rounded bg-primary text-xs font-semibold text-primary-foreground">
                    {shown.n}
                  </span>
                )}
                {sp.title}
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 text-xs text-muted-foreground">{sp.description}</Dialog.Description>
            </div>
            <Dialog.Close
              className="inline-flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
              aria-label={sp.close}
            >
              <X className="size-4" aria-hidden="true" />
            </Dialog.Close>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <div className="bg-muted p-4" aria-busy={load.state === "loading"}>
              {load.state === "loading" && (
                <div
                  role="status"
                  className="flex aspect-[612/792] w-full flex-col items-center justify-center gap-2 rounded-md border border-border bg-background text-sm text-muted-foreground"
                >
                  <Loader2 className="size-5 motion-safe:animate-spin" aria-hidden="true" />
                  {sp.loading}
                </div>
              )}
              {load.state === "error" && (
                <div role="alert" className="flex flex-col items-center gap-3 rounded-md border border-border bg-background p-8 text-center text-sm">
                  <AlertTriangle className="size-5 text-primary" aria-hidden="true" />
                  <p>{sp.error}</p>
                  <button
                    type="button"
                    onClick={() => setAttempt((n) => n + 1)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-primary/40 px-3 py-1 text-xs font-medium text-primary hover:bg-accent dark:text-accent-foreground focus-visible:outline-2 focus-visible:outline-ring"
                  >
                    <RotateCcw className="size-3.5" aria-hidden="true" />
                    {sp.retry}
                  </button>
                </div>
              )}
              {load.state === "ready" && shown && (
                <>
                  {load.data.boxes.length === 0 && (
                    <p role="status" className="mb-3 rounded-md bg-warning p-2 text-xs text-warning-foreground">
                      {sp.notFound}
                    </p>
                  )}
                  <div className="pointer-events-none sticky top-2 z-10 mb-2 flex justify-end">
                    <button
                      type="button"
                      onClick={() => setZoom((z) => !z)}
                      aria-pressed={zoom}
                      className="pointer-events-auto inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1 text-xs font-medium shadow-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      {zoom ? <ZoomOut className="size-3.5" aria-hidden="true" /> : <ZoomIn className="size-3.5" aria-hidden="true" />}
                      {zoom ? sp.zoomOut : sp.zoomIn}
                    </button>
                  </div>
                  <PageImage zoom={zoom} key={`${load.data.imageUrl}|${JSON.stringify(load.data.boxes)}`} data={load.data} alt={sp.pageAlt(shown.docSubtitle, shown.pdfPage)} />
                </>
              )}
            </div>

            {shown && (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 px-5 py-4 text-sm">
                <dt className="text-muted-foreground">{sp.document}</dt>
                <dd className="flex min-w-0 items-center gap-1.5 font-bold">
                  <FileText className="size-3.5 shrink-0 text-primary" aria-hidden="true" />
                  <bdi>{shown.docSubtitle}</bdi>
                </dd>
                <dt className="text-muted-foreground">{sp.page}</dt>
                <dd>{page}</dd>
                <dt className="text-muted-foreground">{sp.section}</dt>
                <dd>
                  <bdi>{shown.section}</bdi>
                </dd>
                <dt className="text-muted-foreground">{sp.quote}</dt>
                <dd>
                  <blockquote
                    dir="ltr"
                    lang="en"
                    className="border-s-2 border-primary ps-3 text-[13px] leading-6 text-foreground/90 [overflow-wrap:anywhere]"
                  >
                    “{shown.quote}”
                  </blockquote>
                </dd>
              </dl>
            )}
          </div>

          <footer className="border-t border-border px-5 py-2 text-[11px] text-muted-foreground">{s.prototype}</footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
