import * as React from "react";
import { FileBarChart, Languages, Moon, RotateCcw, Sun } from "lucide-react";

import { ChatPanel } from "@/components/chat/chat-panel";
import { type ExecutiveReport, ExecutiveReportView } from "@/components/report/executive-report";
import { ParticleTitle } from "@/components/ui/particle-title";
import { SectionHeading } from "@/components/ui/section-heading";
import type { Lang } from "@/lib/api";
import { DOCUMENTS, EXAMPLES, dirOf, t } from "@/lib/i18n";

const initialLang = (): Lang => (document.documentElement.lang === "en" ? "en" : "ar"); // UI_DEFAULT_LANG=ar

/*
 * Layout follows almamlakatv.com (owner request, 2026-10-15): two-tier white header with the red logo,
 * a red pill action button and a grey sun/moon toggle; a navy-labelled "trending" strip (here: example
 * questions); red-bar section headings; small, sharp corners; Almamlaka's own typeface.
 */
export default function App() {
  const [lang, setLang] = React.useState<Lang>(initialLang);
  // Follows the device's light/dark setting until the viewer picks one with the toggle (remembered per browser).
  const [dark, setDark] = React.useState(() => {
    try {
      const saved = localStorage.getItem("almamlaka-theme");
      if (saved === "dark" || saved === "light") return saved === "dark";
    } catch {
      /* storage blocked: fall back to the device setting */
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  });
  const [resetKey, setResetKey] = React.useState(0);
  const [demo, setDemo] = React.useState(false);
  const [starter, setStarter] = React.useState<string | null>(null);
  const [reportOpen, setReportOpen] = React.useState(false);
  const [report, setReport] = React.useState<ExecutiveReport | null>(null);
  const s = t(lang);

  React.useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dirOf(lang);
    document.title = s.appName;
  }, [lang, s.appName]);

  React.useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const chooseTheme = (next: boolean) => {
    setDark(next);
    try {
      localStorage.setItem("almamlaka-theme", next ? "dark" : "light");
    } catch {
      /* storage blocked: the choice lasts for this visit only */
    }
  };

  async function openReport() {
    setReportOpen(true);
    try {
      const response = await fetch(`/api/report?lang=${lang}`, { credentials: "same-origin" });
      setReport(response.ok ? ((await response.json()) as ExecutiveReport) : null);
    } catch {
      setReport(null); // no backend yet: the view shows the report template outline
    }
  }

  const container = "mx-auto w-full max-w-6xl px-4";

  return (
    <div className="flex min-h-svh flex-col bg-background text-foreground">
      <header className="sticky top-0 z-40 bg-background">
        {/* Tier 1: logo and title, utility link */}
        <div className="border-b border-border">
          <div className={`${container} flex items-center gap-4 py-2.5`}>
            <img src="/brand/almamlaka-logo.webp" alt="قناة المملكة" width={159} height={47} className="h-10 w-auto dark:brightness-125" />
            <span className="hidden border-s border-border ps-4 text-base font-bold sm:inline">{s.appName}</span>
            <button
              type="button"
              onClick={() => setLang(lang === "ar" ? "en" : "ar")}
              lang={lang === "ar" ? "en" : "ar"}
              className="ms-auto inline-flex items-center gap-1.5 text-sm font-medium hover:text-primary focus-visible:outline-2 focus-visible:outline-ring"
            >
              <Languages className="size-4" aria-hidden="true" />
              {s.language}
            </button>
          </div>
        </div>
        {/* Tier 2: actions, like the site's nav row with the red "live" pill */}
        <div className="border-b border-border">
          <div className={`${container} flex items-center gap-2 py-2`}>
            <button
              type="button"
              onClick={() => setResetKey((k) => k + 1)}
              className="inline-flex items-center gap-1.5 px-1 text-sm font-medium hover:text-primary focus-visible:outline-2 focus-visible:outline-ring"
            >
              <RotateCcw className="size-4" aria-hidden="true" />
              {s.newChat}
            </button>
            <div className="ms-auto flex items-center gap-2">
              <div role="group" aria-label="Theme" className="flex rounded-md bg-muted p-0.5">
                <button
                  type="button"
                  aria-pressed={!dark}
                  aria-label="Light theme"
                  onClick={() => chooseTheme(false)}
                  className={`rounded p-1.5 ${!dark ? "bg-background shadow-sm" : "text-muted-foreground"}`}
                >
                  <Sun className="size-4" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  aria-pressed={dark}
                  aria-label="Dark theme"
                  onClick={() => chooseTheme(true)}
                  className={`rounded p-1.5 ${dark ? "bg-background shadow-sm" : "text-muted-foreground"}`}
                >
                  <Moon className="size-4" aria-hidden="true" />
                </button>
              </div>
              <button
                type="button"
                onClick={() => void openReport()}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-bold text-primary-foreground hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                <FileBarChart className="size-4" aria-hidden="true" />
                {s.report}
              </button>
            </div>
          </div>
        </div>
        <p className="bg-brand-navy px-4 py-1 text-center text-[11px] text-white/90">{s.prototype}</p>
        {demo && (
          <p role="status" className="bg-warning px-4 py-1.5 text-center text-xs text-warning-foreground">
            {s.demoBanner}
          </p>
        )}
      </header>

      {/* "Trending now" strip, used for example questions */}
      <div className={`${container} mt-4 flex flex-wrap items-stretch gap-x-5 gap-y-2`}>
        <span className="inline-flex items-center rounded-sm bg-brand-navy px-3 py-1.5 text-sm font-bold text-white">
          {s.examplesTitle}
        </span>
        {EXAMPLES[lang].map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => setStarter(q === starter ? `${q} ` : q)}
            className="inline-flex items-center gap-2 text-sm font-bold hover:text-primary focus-visible:outline-2 focus-visible:outline-ring"
          >
            <span aria-hidden="true" className="size-2.5 rounded-full bg-primary/60" />
            {q}
          </button>
        ))}
      </div>

      <main className={`${container} grid flex-1 gap-6 py-4 lg:grid-cols-[minmax(0,1fr)_300px]`}>
        <section className="flex min-h-[70svh] flex-col gap-3">
          <ParticleTitle key={lang} text={s.heroTitle} className="h-[96px] sm:h-[160px]" />
          <div className="min-h-0 flex-1">
            <ChatPanel uiLang={lang} resetKey={resetKey} onDemo={setDemo} starter={starter} />
          </div>
        </section>

        <aside className="space-y-5 text-sm">
          <div>
            <SectionHeading>{s.docsTitle}</SectionHeading>
            <ul className="mt-3 space-y-2">
              {DOCUMENTS[lang].map((d) => (
                <li key={d.id} className="flex items-center gap-2 rounded-md bg-muted px-3 py-3 font-bold">
                  <span className="rounded-sm bg-primary px-1.5 py-0.5 text-[10px] text-primary-foreground" dir="ltr">
                    {d.id}
                  </span>
                  {d.name}
                </li>
              ))}
            </ul>
          </div>
          <p className="leading-7 text-muted-foreground">{s.tagline}</p>
        </aside>
      </main>

      <footer className="border-t border-border px-4 py-3 text-center text-[11px] leading-5 text-muted-foreground">
        {s.footer}
      </footer>

      {reportOpen && <ExecutiveReportView report={report} lang={lang} onClose={() => setReportOpen(false)} />}
    </div>
  );
}
