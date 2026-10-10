"""FastAPI application factory.

Run locally:  uvicorn app.main:app --reload --port 8000   (from the backend/ directory)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import Settings, get_settings
from app.db import Database
from app.services.analysis_service import AnalysisService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details}})


def create_app(settings: Settings | None = None, *, db: Database | None = None,
               serpapi_transport: httpx.BaseTransport | None = None,
               llm_transport: httpx.BaseTransport | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = db or Database(settings.resolved_database_url)
    db.create_all()
    service = AnalysisService(db, settings, serpapi_transport=serpapi_transport, llm_transport=llm_transport)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        service.shutdown()

    app = FastAPI(title="MarketSim AI", version="0.1.0", lifespan=lifespan,
                  description="Autonomous multi-agent business intelligence and strategy simulator.")
    app.state.settings = settings
    app.state.db = db
    app.state.service = service
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["GET", "POST", "PUT"],
                       allow_headers=["Content-Type"])

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return _error(exc.status_code, exc.detail["code"], exc.detail.get("message", ""), exc.detail.get("details"))
        return _error(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        message = "; ".join(str(d["msg"]).removeprefix("Value error, ") for d in details[:5])
        return _error(422, "validation_error", message or "Invalid request.", details)

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception):  # pragma: no cover
        logging.getLogger("marketsim").exception("Unhandled error")
        return _error(500, "internal_error", "An unexpected error occurred.")

    app.include_router(router)
    return app


_app: FastAPI | None = None


def __getattr__(name: str):
    """Lazily build ``app`` so importing create_app (e.g. in tests) has no side effects."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
