"""Fábrica da aplicação FastAPI."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from evasao_ti import __version__
from evasao_ti.api.routes import router
from evasao_ti.config import Settings, get_settings
from evasao_ti.logging_setup import configure_logging, get_logger
from evasao_ti.storage.repository import Repository, WarehouseUnavailable

log = get_logger("api")

DESCRIPTION = """
Estatísticas de matrículas e trancamentos em cursos de graduação, calculadas a partir dos
**Microdados do Censo da Educação Superior (INEP)** e classificadas pela **CINE Brasil**.

* Unidade: vínculos aluno-curso por ano (não pessoas).
* Taxas: razão de somas (nunca média de percentuais).
* Anos sem dados aparecem em `meta.periodo.anos_ausentes` — nunca como zero.
* Os números são calculados por este projeto e **não** são estatísticas oficiais do INEP.

Metodologia completa: `GET /api/v1/methodology`.
"""


def _error(status: int, code: str, message: str, details: object = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    app = FastAPI(
        title="API Evasão em TI — Censo da Educação Superior",
        version=__version__,
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.repository = Repository(settings.warehouse_path)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.exception_handler(WarehouseUnavailable)
    async def _no_data(_: Request, exc: WarehouseUnavailable) -> JSONResponse:
        return _error(503, "dados_indisponiveis", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return _error(422, "parametro_invalido", "Parâmetros inválidos", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "nao_encontrado", 405: "metodo_nao_permitido", 422: "parametro_invalido"}
        return _error(exc.status_code, code.get(exc.status_code, "erro"), str(exc.detail))

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("erro inesperado", exc_info=exc)
        return _error(500, "erro_interno", "Erro interno inesperado")

    app.include_router(router)
    return app
