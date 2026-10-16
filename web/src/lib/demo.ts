/**
 * Demo transport: canned turns so the UI can be reviewed before the M4 backend exists.
 * Used only when the backend is unreachable in development, and always labelled on screen
 * as demo data. The quotes are verbatim from the corpus (data/index/chunks.jsonl), so the
 * examples show exactly what a real verified answer looks like.
 */
import type { AssistantTurn, Citation, Lang, StreamEvent } from "@/lib/api";
import { detectLang } from "@/lib/i18n";

const C1_OVR: Omit<Citation, "n"> = {
  chunkId: "OVR-p1-s3",
  docId: "OVR",
  docSubtitle: "Project Overview Document",
  file: "Almamlaka_Project_Overview.pdf",
  pdfPage: 1,
  printedLabel: null,
  section: "3. Key Details",
  quote: "Total Approved Budget: $2,400,000",
};
const C1_BUD: Omit<Citation, "n"> = {
  chunkId: "BUD-p1-s2",
  docId: "BUD",
  docSubtitle: "Budget & Timeline Breakdown",
  file: "Almamlaka_Budget_Timeline.pdf",
  pdfPage: 1,
  printedLabel: null,
  section: "2. Budget Notes",
  quote:
    "Following a revision by the Finance Committee in December 2026, the total project budget was adjusted to $2,600,000",
};

const trace = (retrieved: string[], verified: number) => ({
  documentsSearched: ["OVR", "BUD", "GOV"],
  searches: ["Total Approved Budget", "budget revised Finance Committee"],
  retrieved,
  claimsVerified: verified,
  claimsRemoved: 0,
  denseFallback: false,
  ms: 4200,
});

function budgetTurn(lang: Lang): AssistantTurn {
  const ar = lang === "ar";
  return {
    id: crypto.randomUUID(),
    lang,
    status: "answered",
    flags: ["conflict"],
    claims: [
      {
        kind: "conflict_position",
        text: ar
          ? "تذكر وثيقة نظرة عامة على المشروع أن إجمالي الميزانية المعتمدة هو ‎$2,400,000‎."
          : "The Project Overview states a Total Approved Budget of $2,400,000.",
        citations: [1],
      },
      {
        kind: "conflict_position",
        text: ar
          ? "وتذكر وثيقة الميزانية والجدول الزمني أن لجنة المالية عدّلت الميزانية الإجمالية في كانون الأول/ديسمبر 2026 إلى ‎$2,600,000‎."
          : "The Budget & Timeline Breakdown says the Finance Committee revised the total budget to $2,600,000 in December 2026.",
        citations: [2],
      },
    ],
    conflicts: [
      {
        topic: ar ? "إجمالي ميزانية المشروع" : "Total project budget",
        positions: [
          { text: "$2,400,000", citations: [1] },
          { text: "$2,600,000", citations: [2] },
        ],
      },
    ],
    missing: [],
    clarify: null,
    message: "",
    citations: [
      { n: 1, ...C1_OVR },
      { n: 2, ...C1_BUD },
    ],
    trace: trace(["OVR-p1-s3", "BUD-p1-s2", "BUD-p1-s1", "GOV-p1-s2"], 2),
    signature: "demo",
  };
}

function notInDocsTurn(lang: Lang): AssistantTurn {
  return {
    id: crypto.randomUUID(),
    lang,
    status: "not_in_documents",
    flags: [],
    claims: [
      {
        kind: "absence",
        text:
          lang === "ar"
            ? "لا تذكر الوثائق الثلاث هذه المعلومة."
            : "The three documents don't provide this information.",
        citations: [],
      },
    ],
    conflicts: [],
    missing: [],
    clarify: null,
    message: "",
    citations: [],
    trace: trace([], 0),
    signature: "demo",
  };
}

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const id = window.setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      window.clearTimeout(id);
      reject(new DOMException("aborted", "AbortError"));
    });
  });

export async function* demoChat(message: string, signal: AbortSignal): AsyncGenerator<StreamEvent> {
  const lang = detectLang(message);
  const turn = /budget|ميزاني|mizani/i.test(message) ? budgetTurn(lang) : notInDocsTurn(lang);
  for (const stage of ["planning", "retrieving", "answering", "verifying"] as const) {
    yield { type: "stage", stage };
    await sleep(550, signal);
  }
  for (const claim of turn.claims) {
    yield { type: "claim", claim, citations: turn.citations.filter((c) => claim.citations.includes(c.n)) };
    await sleep(350, signal);
  }
  yield { type: "final", turn };
}
