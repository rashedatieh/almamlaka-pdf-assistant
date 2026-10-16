/**
 * Contract between the UI and POST /api/chat (Server-Sent Events) — PROJECT_PLAN §3.1 "API", §4.1 step 6.
 *
 * Citations are built by the server from chunk metadata; the UI never invents page numbers
 * (non-negotiable 2). Every text field is rendered with React text nodes only (no innerHTML),
 * so model output can never become markup (non-negotiable 8).
 */

export type Lang = "ar" | "en";
export type Status =
  | "answered"
  | "partial"
  | "not_in_documents"
  | "clarify"
  | "out_of_scope"
  | "greeting_or_help"
  | "error";
export type Flag = "conflict" | "premise_contradicted" | "derived";
export type Stage = "planning" | "retrieving" | "answering" | "verifying";

export type Citation = {
  n: number; // display number, 1-based, unique within a turn
  chunkId: string; // e.g. "BUD-p1-s2"
  docId: string;
  docSubtitle: string; // "Budget & Timeline Breakdown"
  file: string;
  pdfPage: number;
  printedLabel: string | null; // shown only when real and different from pdfPage
  section: string; // "2. Budget Notes"
  quote: string; // verbatim from the PDF, verified server-side
  // Character offsets of `quote` in the chunk text, for the evidence spotlight (app/pipeline/render.py).
  // Always sent by the server; optional only so canned demo citations can omit them (the spotlight
  // then asks the server to locate the quote).
  start?: number;
  end?: number;
};

/** GET /api/sources/spotlight (app/sources_api.py): the page image and highlight boxes in image pixels. */
export type SpotlightBox = { x: number; y: number; w: number; h: number };
export type Spotlight = {
  chunkId: string;
  docId: string;
  pdfPage: number;
  section: string;
  imageUrl: string; // same-origin /api/sources/page/{doc}/{page}.png
  width: number;
  height: number;
  boxes: SpotlightBox[];
};

export async function fetchSpotlight(c: Citation, signal: AbortSignal): Promise<Spotlight> {
  const params = new URLSearchParams({ chunk: c.chunkId });
  if (c.start !== undefined && c.end !== undefined && c.end > c.start) {
    params.set("start", String(c.start));
    params.set("end", String(c.end));
  } else {
    params.set("quote", c.quote);
  }
  const response = await fetch(`/api/sources/spotlight?${params}`, { credentials: "same-origin", signal });
  if (!response.ok) throw new Error(String(response.status));
  return (await response.json()) as Spotlight;
}

export type ClaimKind = "fact" | "derived" | "conflict_position" | "absence" | "framing";
export type Claim = { text: string; kind: ClaimKind; citations: number[] };
export type ConflictPosition = { text: string; citations: number[] };
export type Conflict = { topic: string; positions: ConflictPosition[] };

export type Trace = {
  documentsSearched: string[]; // doc IDs
  searches: string[]; // planner queries actually run
  retrieved: string[]; // chunk IDs, ranked
  claimsVerified: number;
  claimsRemoved: number;
  denseFallback: boolean;
  ms: number;
};

export type AssistantTurn = {
  id: string;
  lang: Lang;
  status: Status;
  flags: Flag[];
  claims: Claim[];
  conflicts: Conflict[];
  missing: string[];
  clarify: { question: string; options: string[] } | null;
  message: string; // template text for out_of_scope / greeting / error; "" otherwise
  citations: Citation[];
  trace: Trace | null;
  signature: string; // HMAC over the turn; sent back as history
};

export type StreamEvent =
  | { type: "stage"; stage: Stage }
  | { type: "claim"; claim: Claim; citations: Citation[] }
  | { type: "final"; turn: AssistantTurn }
  | { type: "error"; code: string; message: string };

export type HistoryItem = { role: "user" | "assistant"; text: string; signature?: string };

/** Parse one SSE frame ("data: {...}") into a StreamEvent; ignores comments and keep-alives. */
export function parseFrame(frame: string): StreamEvent | null {
  const data = frame
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  if (!data) return null;
  const event = JSON.parse(data) as StreamEvent;
  return event && typeof event === "object" && "type" in event ? event : null;
}

/** Stream a chat turn from the backend. Yields events until the server closes the stream. */
export async function* streamChat(
  message: string,
  history: HistoryItem[],
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify({ message, history }),
    credentials: "same-origin",
    signal,
  });
  if (!response.ok || !response.body) {
    yield { type: "error", code: String(response.status), message: response.statusText };
    return;
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const event = parseFrame(buffer.slice(0, cut));
      buffer = buffer.slice(cut + 2);
      if (event) yield event;
    }
  }
}
