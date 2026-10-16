"""Executive report as a print-quality PDF (ADR D24): the file tools.report_pdf built from the saved report.

  GET /api/report.pdf?lang=en|ar  -> application/pdf download
      ("Almamlaka-DEI-Executive-Report-<LANG>.pdf"), 404 when that PDF has not been built

The PDF ships with the app next to its report JSON (data/reports/executive-<lang>-<key>.pdf, same key), so
serving it costs nothing and never calls a model. It needs the reviewer invite when one is configured (401
otherwise). The integrator mounts the router with `app.include_router(make_router(svc.invited))`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.pipeline import report as reports


def saved_pdf(lang: str) -> Path:
    """The PDF for the current corpus, template and model: the report JSON's path with a .pdf suffix."""
    return reports.report_path(lang).with_suffix(".pdf")


def make_router(invited: Callable[[Request], bool], locate: Callable[[str], Path] = saved_pdf) -> APIRouter:
    router = APIRouter()

    @router.get("/api/report.pdf")
    def report_pdf(request: Request, lang: Literal["en", "ar"] = "en") -> FileResponse:
        if not invited(request):
            raise HTTPException(401, "invite required")
        path = locate(lang)
        if not path.is_file():
            raise HTTPException(404, "report PDF not built yet")
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=f"Almamlaka-DEI-Executive-Report-{lang.upper()}.pdf",
            content_disposition_type="attachment",
            headers={"Cache-Control": "private, no-cache"},
        )

    return router
