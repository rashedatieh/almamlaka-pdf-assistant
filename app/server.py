"""FastAPI service (PROJECT_PLAN §3.1 "API"): chat over Server-Sent Events, the saved executive report, and
the built UI (web/dist) as static files. One Cloud Run service, no CDN.

  POST /api/chat     {message, history} -> SSE frames "data: <StreamEvent JSON>\\n\\n" (web/src/lib/api.ts)
  GET  /api/report   ?lang=en|ar -> the saved ExecutiveReport, or 404 (the UI then shows the outline)
  GET  /health       liveness (Cloud Run reserves /healthz)
  GET  /?invite=…    sets the reviewer cookie and redirects to "/" (only when an invite token is configured)

History is client-held. Assistant turns are accepted only with a valid HMAC signature issued by this
server, so a client cannot plant fake assistant messages in the planner's context (non-negotiable 8).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from app import report_pdf_api, sources_api
from app.budget import DailyBudget
from app.lang import detect
from app.llm.client import LLMClient
from app.pipeline import report as reports
from app.pipeline.orchestrator import Engine, Settings
from app.pipeline.planner import Turn
from app.pipeline.render import render_turn
from app.retrieval.conflicts import load_conflict_groups
from app.retrieval.retriever import Retriever

log = logging.getLogger("almamlaka.server")
ROOT = Path(__file__).resolve().parents[1]
DIST = Path(os.environ.get("WEB_DIST", ROOT / "web" / "dist"))
COOKIE = "almamlaka_invite"
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


class HistoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: Literal["user", "assistant"]
    text: str = Field(max_length=8000)
    signature: str = ""


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: str = Field(max_length=4000)  # the engine refuses > MAX_INPUT_CHARS with a bilingual message
    history: list[HistoryItem] = Field(default_factory=list, max_length=200)


def _secrets() -> dict[str, str]:
    raw = os.environ.get("APP_SECRETS", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("APP_SECRETS is not valid JSON") from exc
    return {k: str(v) for k, v in data.items() if isinstance(v, str | int)}


def plain_text(turn: dict[str, Any]) -> str:
    """What the UI sends back as an assistant history item (chat-panel.tsx plainText)."""
    return " ".join(t for t in [turn.get("message", ""), *(c["text"] for c in turn.get("claims", []))] if t)


class HistoryInvalid(Exception):
    """An assistant turn in the client's history was not signed by this server."""


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True


def dense_leg(chunks: dict[str, dict[str, Any]]) -> Any:
    """The dense (embedding) leg when DENSE_ENABLED=true, else None (ADR-0001 D26: measured, shipped off).

    It needs the committed corpus vectors for EMBEDDING_MODEL and GCP_PROJECT / VERTEX_LOCATION for query
    embeddings. Any problem at start-up leaves retrieval on BM25 alone, and any failure or timeout of a
    query embedding falls back to BM25 for that turn (app.retrieval.retriever).
    """
    env = os.environ
    if env.get("DENSE_ENABLED", "false").lower() != "true":
        return None
    from app.retrieval.dense import DenseLeg, VectorStore, VertexEmbedder, load_vectors

    try:
        model = env.get("EMBEDDING_MODEL", "gemini-embedding-2")
        timeout = float(env.get("DENSE_TIMEOUT_S", "1.5"))
        ids = list(chunks)
        sha = json.loads((reports.INDEX / "manifest.json").read_text(encoding="utf-8"))["chunks_sha256"]
        store = VectorStore(ids, load_vectors(model, ids, sha))
        embedder = VertexEmbedder(
            model, env.get("GCP_PROJECT", ""), env.get("VERTEX_LOCATION", "global"), timeout_s=timeout
        )
        return DenseLeg(
            embedder, store, min_similarity=float(env.get("DENSE_MIN_SIMILARITY", "0.0")), timeout_s=timeout
        )
    except Exception as exc:  # misconfiguration must never stop the service: BM25 still answers
        log.warning("dense leg disabled: %s", type(exc).__name__)
        return None


class Service:
    def __init__(self, engine: Engine | None = None) -> None:
        env = os.environ
        app_secrets = _secrets()
        self.app_env = env.get("APP_ENV", "dev")
        # INVITE_REQUIRED=false opens the chat to anyone with the link. Spend stays capped by
        # DAILY_BUDGET_USD, the per-IP rate limit and the Anthropic workspace limit.
        # Old ?invite= links still work.
        required = env.get("INVITE_REQUIRED", "true").lower() != "false"
        self.invite = app_secrets.get("invite_token", "") if required else ""
        key = app_secrets.get("session_secret", "")
        if not key:
            if self.app_env != "dev":
                raise RuntimeError("APP_SECRETS.session_secret is required outside dev")
            key = secrets.token_hex(32)  # dev only: signatures last for this process
        self.key = key.encode()
        self.max_history = int(env.get("MAX_HISTORY_TURNS", "6"))
        self.limiter = RateLimiter(int(env.get("RATE_LIMIT_PER_MIN", "10")))
        if engine is None:
            client = LLMClient()
            if self.app_env != "dev" and client.mode != "live":
                raise RuntimeError("staging and prod must run with LLM_MODE=live")
            chunks = reports.load_chunks()
            engine = Engine(
                client=client,
                retriever=Retriever(
                    list(chunks.values()), dense=dense_leg(chunks), top_k=int(env.get("RETRIEVAL_TOP_K", "8"))
                ),
                chunks=chunks,
                budget=DailyBudget(float(env.get("DAILY_BUDGET_USD", "1.00"))),
                settings=Settings.from_env(),
                conflict_groups=load_conflict_groups(known=set(chunks)),
            )
        self.engine = engine

    def sign(self, text: str) -> str:
        return hmac.new(self.key, text.encode("utf-8"), hashlib.sha256).hexdigest()

    def invited(self, request: Request) -> bool:
        if not self.invite:
            return True
        return hmac.compare_digest(request.cookies.get(COOKIE, ""), self.sign("invite:" + self.invite))

    def history(self, items: list[HistoryItem]) -> tuple[list[Turn], int]:
        """The history as planner turns, with the number of user turns so far.

        Every assistant turn must carry this server's signature over its exact text. A forged, altered or
        unsigned assistant turn rejects the whole request (HTTP 400 history_invalid, ACCEPTANCE G-07): the
        UI then resets the conversation, so nothing we did not say can enter the planner's context.
        """
        turns: list[Turn] = []
        for item in items:
            if item.role == "assistant" and not hmac.compare_digest(item.signature, self.sign(item.text)):
                raise HistoryInvalid
            turns.append(Turn(item.role, item.text))
        users = sum(1 for t in turns if t.role == "user")
        return turns[-2 * self.max_history :], users

    def stream(self, message: str, history: list[Turn], turns_so_far: int) -> Iterator[str]:
        try:
            for event in self.engine.run(message, history, turns_so_far):
                if event["type"] == "error":  # guard refusals (too_long, turn_cap, budget_exhausted)
                    turn = render_turn(
                        lang=event.get("lang") or detect(message),  # the language its message is in
                        status="error",
                        claims=[],
                        conflicts=[],
                        chunks={},
                        message=event["message"],
                    )
                    event = {"type": "final", "turn": turn}
                if event["type"] == "final":
                    event["turn"]["signature"] = self.sign(plain_text(event["turn"]))
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:
            log.exception("chat stream failed")  # no message content in logs (non-negotiable 7)
            yield 'data: {"type": "error", "code": "internal", "message": ""}\n\n'


def client_ip(request: Request) -> str:
    """The address Cloud Run's front end saw. It appends that address as the LAST X-Forwarded-For entry;
    earlier entries come from the client and can be forged, so they never key the rate limit."""
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    return hops[-1] if hops else (request.client.host if request.client else "unknown")


def create_app(service: Service | None = None) -> FastAPI:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    svc = service or Service()
    app = FastAPI(title="Almamlaka TV document assistant", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    favicon = DIST / "brand" / "almamlaka-favicon.png"

    @app.get("/favicon.ico", include_in_schema=False)
    @app.get("/apple-touch-icon.png", include_in_schema=False)
    @app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
    def icon() -> Response:
        if not favicon.is_file():
            raise HTTPException(404, "no icon")
        return FileResponse(
            favicon, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"}
        )

    @app.get("/health")
    @app.get("/healthz")  # Cloud Run's front end reserves paths ending in "z"; use /health there
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/chat")
    def chat(body: ChatRequest, request: Request) -> Response:
        if not svc.invited(request):
            raise HTTPException(401, "invite required")
        if not svc.limiter.allow(client_ip(request)):
            raise HTTPException(429, "too many requests")
        try:
            history, turns_so_far = svc.history(body.history)
        except HistoryInvalid:
            log.warning("history_invalid: unsigned or altered assistant turn")  # no content logged
            raise HTTPException(400, "history_invalid") from None
        return StreamingResponse(
            svc.stream(body.message, history, turns_so_far),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/report")
    def report(request: Request, lang: Literal["en", "ar"] = "en") -> JSONResponse:
        if not svc.invited(request):
            raise HTTPException(401, "invite required")
        saved = reports.load(lang)
        if saved is None:
            raise HTTPException(404, "report not generated yet")
        return JSONResponse(saved)

    app.include_router(report_pdf_api.make_router(svc.invited))  # GET /api/report.pdf (pre-built PDF)
    app.include_router(sources_api.make_router(svc.invited))  # evidence spotlight: page images + boxes

    index = DIST / "index.html"

    @app.get("/")
    def home(invite: str = "") -> Response:
        if invite and svc.invite and hmac.compare_digest(invite, svc.invite):
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(
                COOKIE,
                svc.sign("invite:" + svc.invite),
                max_age=60 * 60 * 24 * 30,
                httponly=True,
                secure=svc.app_env != "dev",
                samesite="lax",
            )
            return response
        if not index.is_file():
            return JSONResponse({"detail": "UI not built: run npm run build in web/"}, status_code=503)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    for folder in ("assets", "brand", "fonts"):
        if (DIST / folder).is_dir():
            app.mount(f"/{folder}", StaticFiles(directory=DIST / folder), name=folder)
    return app


def __getattr__(name: str) -> Any:
    """`uvicorn app.server:app` builds the app on first access, so importing this module stays cheap."""
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
