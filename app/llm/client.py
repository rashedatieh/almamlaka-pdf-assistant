"""Claude API client with record/replay (PROJECT_PLAN §3.1 "LLM dev mode"; ENGINEERING_RULES.md).

LLM_MODE:
  replay  (default; tests and development)  answer from a recorded cassette; no network, no key needed
  record  call the API and save the response as a cassette (explicit, approved runs only)
  live    call the API without saving (staging/prod)

A cassette is keyed by a SHA-256 of the canonical request (model, system, messages, output_config,
thinking, inference_geo), so any prompt or setting change misses the cache instead of replaying a
stale answer. Cassettes store the response text, stop_reason, model and usage. Request headers, API keys
and canary tokens are never written.

Request rules (ADR-0001 §1, D2, D19):
  * structured output via output_config.format (json_schema); effort via output_config.effort
  * no temperature/top_p/top_k (a 400 on these models)
  * thinking at its lowest per model: Haiku 5.5 "disabled", Sonnet 5.5 "between_tools", Opus 5.5 omitted
    (it cannot be turned off; effort is the only control)
  * stop_reason "refusal" or "max_tokens" is a failure, never a partial answer
A failed call that got a response was still billed: its cost is priced from the recorded usage before any
stop_reason or schema check and carried on the LLMError, so the daily budget counts it (Q-01).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.llm.schemas import output_schema
from app.prices import PRICES, cost_usd

CASSETTES_DIR = Path(__file__).resolve().parents[2] / "eval" / "cassettes"
MODES = ("replay", "record", "live")


class LLMError(Exception):
    """The model call failed or returned something unusable; the caller downgrades or errors.

    `cost_usd` is what the failed call was billed (0 when no response came back); `from_cassette` marks a
    replayed failure, which costs nothing today.
    """

    def __init__(self, message: str = "", *, cost_usd: float = 0.0, from_cassette: bool = False) -> None:
        super().__init__(message)
        self.cost_usd = cost_usd
        self.from_cassette = from_cassette


class CassetteMissing(LLMError):
    """Replay mode and no cassette for this exact request. Record it with an approved live run."""


def lowest_thinking(model: str) -> dict[str, str] | None:
    """The least-thinking setting each model accepts (ADR §3.1 row 5c, row 11c)."""
    if model.startswith("claude-haiku-5-5"):
        return {"type": "disabled"}
    if model.startswith("claude-sonnet-5-5"):
        return {"type": "between_tools"}
    if model.startswith("claude-opus-5-5"):
        return None  # always adaptive; sending "disabled" is a 400
    raise LLMError(f"no thinking policy for model {model!r}; add it after checking the ADR")


@dataclass
class LLMResult:
    parsed: BaseModel
    model: str
    stop_reason: str
    usage: dict[str, Any]
    cost_usd: float
    from_cassette: bool


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class LLMClient:
    def __init__(
        self,
        mode: str | None = None,
        inference_geo: str | None = None,
        timeout_s: float | None = None,
        max_retries: int | None = None,
        cassettes_dir: Path = CASSETTES_DIR,
        sdk: Any = None,
    ) -> None:
        self.mode = mode or os.environ.get("LLM_MODE", "replay")
        if self.mode not in MODES:
            raise LLMError(f"LLM_MODE must be one of {MODES}, not {self.mode!r}")
        self.inference_geo = inference_geo or os.environ.get("INFERENCE_GEO", "global")
        self.timeout_s = timeout_s if timeout_s is not None else float(os.environ.get("LLM_TIMEOUT_S", "45"))
        self.max_retries = (
            max_retries if max_retries is not None else int(os.environ.get("LLM_MAX_RETRIES", "2"))
        )
        self.cassettes_dir = cassettes_dir
        self._sdk = sdk  # injected in tests; created lazily otherwise

    def _client(self) -> Any:
        if self._sdk is None:
            import anthropic  # the key comes from ANTHROPIC_API_KEY (env or Secret Manager)

            self._sdk = anthropic.Anthropic(timeout=self.timeout_s, max_retries=self.max_retries)
        return self._sdk

    def request(
        self,
        route: str,
        model: str,
        system: str,
        user: str,
        output: type[BaseModel],
        effort: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        """The exact Messages API request body (also the cassette key material)."""
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
            "output_config": {
                "effort": effort,
                "format": {"type": "json_schema", "schema": output_schema(output)},
            },
            "inference_geo": self.inference_geo,
        }
        thinking = lowest_thinking(model)
        if thinking is not None:
            body["thinking"] = thinking
        return body

    def cassette_path(self, route: str, body: dict[str, Any]) -> Path:
        key = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()[:32]
        return self.cassettes_dir / route / f"{key}.json"

    def call(
        self,
        route: str,
        model: str,
        system: str,
        user: str,
        output: type[BaseModel],
        effort: str = "low",
        max_tokens: int = 4000,
    ) -> LLMResult:
        body = self.request(route, model, system, user, output, effort, max_tokens)
        path = self.cassette_path(route, body)
        if self.mode == "replay":
            if not path.is_file():
                raise CassetteMissing(
                    f"{route}: no cassette {path.name}; record it with an approved live run"
                )
            recorded = json.loads(path.read_text(encoding="utf-8"))
            return self._result(recorded, output, from_cassette=True)

        recorded = self._live(body)
        if self.mode == "record":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(recorded, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return self._result(recorded, output, from_cassette=False)

    def _live(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client().messages.create(**body)
        except Exception as exc:
            # The SDK is imported only here and in _client(): it takes seconds to import on Windows.
            import anthropic

            if isinstance(exc, anthropic.APIStatusError):
                raise LLMError(f"API error {exc.status_code}") from exc
            if isinstance(exc, anthropic.APIConnectionError):  # includes timeouts, after the SDK's retries
                raise LLMError(f"API connection failed: {type(exc).__name__}") from exc
            raise
        text = next((block.text for block in response.content if block.type == "text"), "")
        usage = response.usage.to_dict() if hasattr(response.usage, "to_dict") else dict(response.usage)
        return {"model": response.model, "stop_reason": response.stop_reason, "text": text, "usage": usage}

    def _result(self, recorded: dict[str, Any], output: type[BaseModel], from_cassette: bool) -> LLMResult:
        usage = recorded.get("usage", {})
        model = recorded["model"]
        if model not in PRICES:
            raise LLMError(f"no price for model {model!r}; add it to app/prices.py from the ADR")
        cost = cost_usd(model, usage, self.inference_geo)  # billed whether or not the response is usable
        if recorded["stop_reason"] in {"refusal", "max_tokens"}:
            raise LLMError(
                f"model stopped with {recorded['stop_reason']}", cost_usd=cost, from_cassette=from_cassette
            )
        try:
            parsed = output.model_validate_json(recorded["text"])
        except ValidationError as exc:
            raise LLMError(
                f"response does not match {output.__name__}", cost_usd=cost, from_cassette=from_cassette
            ) from exc
        return LLMResult(parsed, model, recorded["stop_reason"], usage, cost, from_cassette)
