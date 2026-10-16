/*
 * Executive report (owner decision D24): one branded report across all three documents, generated
 * by Claude Opus 5.5 from a fixed template and verified like chat answers (every statement carries
 * server-built citations; conflicts are reported, never resolved). The corpus is fixed, so the report
 * is generated once and cached server-side; this view only renders it. No current date is shown
 * (non-negotiable 6): the report identifies its source documents instead.
 */
import { Download, FileText, X } from "lucide-react";

import type { Citation, Lang } from "@/lib/api";
import { dirOf, t } from "@/lib/i18n";

export type ReportSection = { id: string; title: string; paragraphs: { text: string; citations: number[] }[] };
export type ExecutiveReport = {
  lang: Lang;
  title: string;
  sections: ReportSection[]; // template order: summary, at a glance, budget, timeline, team & governance, disagreements, risks
  citations: Citation[];
  model: string;
  templateVersion: string;
};

const TEMPLATE: Record<Lang, string[]> = {
  en: ["Executive summary", "Project at a glance", "Budget", "Timeline", "Team & governance", "Where the documents disagree", "Risks"],
  ar: ["الملخص التنفيذي", "المشروع في لمحة", "الميزانية", "الجدول الزمني", "الفريق والحوكمة", "مواضع اختلاف الوثائق", "المخاطر"],
};

export function ExecutiveReportView({ report, lang, onClose }: { report: ExecutiveReport | null; lang: Lang; onClose: () => void }) {
  const s = t(lang);
  return (
    <div role="dialog" aria-modal="true" aria-label={s.report} className="report-dialog fixed inset-0 z-50 overflow-y-auto bg-background/95 backdrop-blur print:static print:bg-white">
      <article dir={dirOf(lang)} lang={lang} className="mx-auto max-w-3xl px-4 py-6 sm:px-8 print:max-w-none print:p-0">
        <header className="mb-6 flex items-start justify-between gap-4 border-b-4 border-primary pb-4">
          <div>
            <img src="/brand/almamlaka-logo.webp" alt="قناة المملكة" width={159} height={47} className="mb-3 h-10 w-auto" />
            <h1 className="text-2xl font-semibold leading-tight">{report?.title ?? s.report}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{s.prototype}</p>
          </div>
          <div className="flex gap-2 print:hidden">
            {/* The pre-built, typeset A4 report (tools/report_pdf.py), identical for every reader and browser. */}
            <a
              href={`/api/report.pdf?lang=${lang}`}
              download
              className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-ring"
            >
              <Download className="size-4" aria-hidden="true" />
              {lang === "ar" ? "تنزيل PDF" : "Download PDF"}
            </a>
            <button type="button" onClick={onClose} className="rounded-lg border border-border p-2 hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring" aria-label="Close">
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
        </header>

        {report ? (
          <>
            {report.sections.map((section) => (
              <section key={section.id} className="mb-6 break-inside-avoid">
                <h2 className="mb-2 border-s-4 border-primary ps-3 text-lg font-semibold">{section.title}</h2>
                {section.paragraphs.map((p, i) => (
                  <p key={i} className="mb-2 leading-7" style={{ unicodeBidi: "plaintext" }}>
                    {p.text}
                    {p.citations.map((n) => (
                      <sup key={n} className="ms-0.5 font-semibold text-primary">[{n}]</sup>
                    ))}
                  </p>
                ))}
              </section>
            ))}
            <section className="mt-8 border-t border-border pt-4 text-sm">
              <h2 className="mb-2 font-semibold">{s.sources}</h2>
              <ol className="space-y-1.5">
                {report.citations.map((c) => (
                  <li key={c.n} className="flex gap-2">
                    <span className="font-semibold text-primary">[{c.n}]</span>
                    <span>
                      <bdi>{c.docSubtitle}</bdi> · {s.pdfPage(c.pdfPage)} · <bdi>{c.section}</bdi> — <q dir="ltr">{c.quote}</q>
                    </span>
                  </li>
                ))}
              </ol>
              <p className="mt-4 text-xs text-muted-foreground" dir="ltr">
                {report.model} · template {report.templateVersion}
              </p>
            </section>
          </>
        ) : (
          <div className="rounded-2xl border border-dashed border-border p-6 text-center">
            <FileText className="mx-auto mb-3 size-8 text-primary" aria-hidden="true" />
            <ol className="mx-auto max-w-sm space-y-1 text-start text-sm text-muted-foreground">
              {TEMPLATE[lang].map((title) => (
                <li key={title}>• {title}</li>
              ))}
            </ol>
          </div>
        )}
      </article>
    </div>
  );
}
