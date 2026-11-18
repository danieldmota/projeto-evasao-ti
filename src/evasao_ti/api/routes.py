"""Endpoints /api/v1. Consultam apenas o warehouse pré-consolidado (nada é baixado aqui)."""

from __future__ import annotations

import json
import math
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from evasao_ti import __version__
from evasao_ti.analytics import queries
from evasao_ti.analytics.indicators import INDICATOR_DEFINITIONS
from evasao_ti.analytics.methodology import (
    AGGREGATION,
    SCOPE,
    SOURCE,
    UNIT,
    methodology_document,
)
from evasao_ti.analytics.queries import Filters, GroupBy, Modalidade, Rede
from evasao_ti.api import schemas as s
from evasao_ti.classification.areas import (
    AREA_LABELS,
    SEGMENTO_LABELS,
    TI_RULE,
    Area,
    Segmento,
)
from evasao_ti.classification.mapping import load_mapping
from evasao_ti.storage.repository import Repository, Snapshot, WarehouseUnavailable

router = APIRouter(prefix="/api/v1")

SMALL_BASE = 100


def get_repo(request: Request) -> Repository:
    return request.app.state.repository


def get_snapshot(repo: Annotated[Repository, Depends(get_repo)]) -> Snapshot:
    return repo.snapshot()


Snap = Annotated[Snapshot, Depends(get_snapshot)]


def common_filters(
    year_start: Annotated[int | None, Query(ge=1995, le=2100, description="Ano inicial")] = None,
    year_end: Annotated[int | None, Query(ge=1995, le=2100, description="Ano final")] = None,
    area: Annotated[list[Area] | None, Query(description="Uma ou mais áreas do projeto")] = None,
    segmento: Annotated[list[Segmento] | None, Query(description="Segmentos (TI separada)")] = None,
    ti: Annotated[
        bool | None, Query(description="true = só TI (CINE 06); false = exceto TI")
    ] = None,
    modalidade: Annotated[Modalidade | None, Query()] = None,
    rede: Annotated[Rede | None, Query()] = None,
    cine_geral: Annotated[
        list[str] | None, Query(pattern=r"^\d{2}$", description="Código(s) CINE área geral")
    ] = None,
) -> Filters:
    if year_start is not None and year_end is not None and year_start > year_end:
        raise HTTPException(status_code=422, detail="year_start deve ser <= year_end")
    return Filters(
        year_start=year_start,
        year_end=year_end,
        areas=area or [],
        segmentos=segmento or [],
        ti=ti,
        modalidade=modalidade,
        rede=rede,
        cine_geral=cine_geral or [],
    )


CommonFilters = Annotated[Filters, Depends(common_filters)]


# ---------------------------------------------------------------- utilidades


def _clean(v: Any) -> Any:
    if v is None or v is pd.NA:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):  # numpy scalar
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    return v


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def _period(snap: Snapshot, f: Filters | None) -> s.Periodo:
    available = sorted(int(y) for y in snap.fact["ano"].unique())
    expected = snap.build_info.get("years_expected") or available
    start = f.year_start if f and f.year_start is not None else min(expected + available)
    end = f.year_end if f and f.year_end is not None else max(expected + available)
    requested = range(start, end + 1)
    with_data = [y for y in available if start <= y <= end]
    missing = [y for y in requested if y not in available]
    return s.Periodo(
        solicitado_inicio=start, solicitado_fim=end, anos_com_dados=with_data, anos_ausentes=missing
    )


def _meta(
    snap: Snapshot,
    f: Filters | None = None,
    extra_filters: dict | None = None,
    avisos: list[str] | None = None,
    paginacao: s.Paginacao | None = None,
    with_period: bool = True,
) -> s.Meta:
    info = snap.build_info
    filtros = {
        k: v
        for k, v in ({**(f.as_dict() if f else {}), **(extra_filters or {})}).items()
        if v is not None
    }
    period = _period(snap, f) if with_period else None
    warnings = list(avisos or [])
    if period and period.anos_ausentes:
        warnings.append(
            f"Sem dados para {period.anos_ausentes}: anos ausentes não são tratados como zero."
        )
    if period and "comparabilidade" in snap.anos:
        attention = snap.anos[
            (snap.anos["comparabilidade"] == "atencao")
            & snap.anos["ano"].isin(period.anos_com_dados)
        ]["ano"].tolist()
        if attention:
            warnings.append(
                f"Anos com alerta de comparabilidade no período: {[int(a) for a in attention]} "
                "(detalhes em /api/v1/years)."
            )
    return s.Meta(
        fonte=s.Fonte(**SOURCE),
        unidade=UNIT,
        escopo=SCOPE,
        metodo={"agregacao": AGGREGATION, "indicadores": INDICATOR_DEFINITIONS},
        periodo=period,
        classificacao=s.Classificacao(
            versao_mapeamento=info.get("mapping_version", ""),
            sha256_mapeamento=info.get("mapping_sha256"),
            regra_ti=TI_RULE,
        ),
        atualizacao=s.Atualizacao(
            build_em=info.get("built_at"), versao_codigo=info.get("code_version")
        ),
        filtros=filtros,
        avisos=warnings,
        paginacao=paginacao,
    )


def _unclassified_warning(snap: Snapshot, f: Filters) -> list[str]:
    df = queries.apply_filters(snap.fact, f)
    total = df["matriculas"].sum(min_count=1)
    if pd.isna(total) or total == 0:
        return []
    nc = df.loc[df["area"] == Area.NAO_CLASSIFICADO.value, "matriculas"].sum()
    low = df.loc[df["confianca"] == "baixa", "matriculas"].sum()
    out = []
    if nc:
        out.append(
            f"{_pct_br(nc / total)} das matrículas do recorte estão em cursos 'Não classificado' "
            "(ex.: Área Básica de Ingresso)."
        )
    if low:
        out.append(
            f"{_pct_br(low / total)} das matrículas do recorte estão em rótulos com "
            "correspondência de confiança 'baixa'."
        )
    return out


def _pct_br(v: float) -> str:
    """Percentual no formato brasileiro (vírgula decimal): 0.0035 -> '0,35%'."""
    return f"{v:.2%}".replace(".", ",")


# ---------------------------------------------------------------- endpoints


@router.get("/health", response_model=s.HealthResponse, tags=["sistema"])
def health(repo: Annotated[Repository, Depends(get_repo)]) -> s.HealthResponse:
    try:
        snap = repo.snapshot()
    except WarehouseUnavailable:
        return s.HealthResponse(status="sem_dados", versao=__version__, warehouse=False)
    return s.HealthResponse(
        status="ok",
        versao=__version__,
        warehouse=True,
        build_em=snap.build_info.get("built_at"),
        anos_disponiveis=snap.build_info.get("years_available", []),
    )


@router.get("/areas", response_model=s.AreasResponse, tags=["classificação"])
def areas(snap: Snap) -> s.AreasResponse:
    counts_area = snap.rotulos.groupby("area").size().to_dict()
    counts_seg = snap.rotulos.groupby("segmento").size().to_dict()
    data = [
        s.AreaInfo(
            codigo=a.value,
            nome=AREA_LABELS[a],
            tipo="area",
            rotulos_cine=int(counts_area.get(a.value, 0)),
        )
        for a in Area
    ] + [
        s.AreaInfo(
            codigo=g.value,
            nome=SEGMENTO_LABELS[g],
            tipo="segmento",
            rotulos_cine=int(counts_seg.get(g.value, 0)),
        )
        for g in Segmento
    ]
    mapping = load_mapping()
    regras = [
        s.RegraMapeamento(
            nivel=r.nivel,
            codigo=r.codigo,
            descricao_cine=r.descricao_cine,
            area=r.area.value,
            confianca=r.confianca,
            justificativa=r.justificativa,
        )
        for r in mapping.rules.values()
    ]
    return s.AreasResponse(data=data, regras=regras, meta=_meta(snap, with_period=False))


@router.get("/years", response_model=s.YearsResponse, tags=["dados"])
def years(snap: Snap) -> s.YearsResponse:
    rows = []
    for r in _records(snap.anos):
        for k in ("avisos", "alertas_automaticos", "notas_curadas"):
            r[k] = json.loads(r[k]) if r.get(k) else []
        r.pop("qualidade", None)
        r.pop("fonte_sha256", None)
        rows.append(s.AnoInfo(**r))
    return s.YearsResponse(data=rows, meta=_meta(snap))


@router.get("/statistics/annual", response_model=s.AnnualResponse, tags=["estatísticas"])
def statistics_annual(
    snap: Snap,
    f: CommonFilters,
    group_by: Annotated[GroupBy, Query(description="Agrupamento das linhas")] = GroupBy.area,
) -> s.AnnualResponse:
    df = queries.annual(snap.fact, f, group_by).sort_values(["ano", "grupo_codigo"])
    return s.AnnualResponse(
        data=[s.LinhaAnual(**r) for r in _records(df)],
        meta=_meta(snap, f, {"group_by": group_by.value}, _unclassified_warning(snap, f)),
    )


@router.get("/statistics/summary", response_model=s.SummaryResponse, tags=["estatísticas"])
def statistics_summary(
    snap: Snap,
    f: CommonFilters,
    group_by: Annotated[GroupBy, Query()] = GroupBy.area,
) -> s.SummaryResponse:
    df, _years = queries.summary(snap.fact, f, group_by)
    df = df.sort_values("grupo_codigo")
    avisos = [
        "Consolidado = soma de vínculos-ano de todos os anos com dados no período. Não representa "
        "número de pessoas distintas.",
        *_unclassified_warning(snap, f),
    ]
    return s.SummaryResponse(
        data=[s.LinhaResumo(**r) for r in _records(df)],
        meta=_meta(snap, f, {"group_by": group_by.value}, avisos),
    )


SORTABLE = {"matriculas", "trancadas", "taxa_trancamento", "no_cine_rotulo", "desvinculados"}


@router.get("/statistics/courses", response_model=s.CoursesResponse, tags=["estatísticas"])
def statistics_courses(
    snap: Snap,
    f: CommonFilters,
    q: Annotated[
        str | None, Query(min_length=2, max_length=80, description="Busca no nome CINE do curso")
    ] = None,
    rotulo: Annotated[list[str] | None, Query(pattern=r"^\d{4}[A-Z]\d{2}$")] = None,
    min_denominador: Annotated[int, Query(ge=0)] = 0,
    sort_by: Annotated[str, Query(description=f"Um de {sorted(SORTABLE)}")] = "matriculas",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> s.CoursesResponse:
    if sort_by not in SORTABLE:
        raise HTTPException(status_code=422, detail=f"sort_by deve ser um de {sorted(SORTABLE)}")
    f.q = q
    f.rotulos = rotulo or []
    df = queries.courses(snap.fact, f)
    if min_denominador:
        df = df[df["denominador_trancamento"].fillna(0) >= min_denominador]
    df = df.sort_values(sort_by, ascending=(order == "asc"), na_position="last")
    total = len(df)
    page = df.iloc[offset : offset + limit].copy()
    page["area_nome"] = page["area"].map(lambda a: AREA_LABELS[Area(a)])
    page["base_pequena"] = page["denominador_trancamento"].fillna(0) < SMALL_BASE
    rows = []
    for r in _records(page):
        r["is_ti"] = bool(r["is_ti"])
        r["confianca"] = r.get("confianca") or "nenhuma"
        rows.append(s.LinhaCurso(**r))
    return s.CoursesResponse(
        data=rows,
        meta=_meta(
            snap,
            f,
            {"min_denominador": min_denominador or None, "sort_by": sort_by, "order": order},
            ["Agregação por rótulo CINE (nome padronizado do curso), somando todas as IES."],
            s.Paginacao(total=total, limit=limit, offset=offset),
        ),
    )


@router.get("/classification/rotulos", response_model=s.RotulosResponse, tags=["classificação"])
def classification_rotulos(
    snap: Snap,
    area: Annotated[list[Area] | None, Query()] = None,
    ti: Annotated[bool | None, Query()] = None,
    confianca: Annotated[str | None, Query(pattern="^(alta|media|baixa|nenhuma)$")] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=80)] = None,
) -> s.RotulosResponse:
    df = snap.rotulos.copy()
    if area:
        df = df[df["area"].isin([a.value for a in area])]
    if ti is not None:
        df = df[df["is_ti"] == ti]
    if confianca:
        df = df[df["confianca"].fillna("nenhuma") == confianca]
    if q:
        needle = queries.normalize_text(q)
        df = df[
            df["no_cine_rotulo"]
            .fillna("")
            .map(queries.normalize_text)
            .str.contains(needle, regex=False)
        ]
    rows = []
    for r in _records(df):
        r["anos"] = [int(x) for x in str(r.get("anos") or "").split(",") if x]
        r["is_ti"] = bool(r["is_ti"])
        r["confianca"] = r.get("confianca") or "nenhuma"
        rows.append(s.RotuloInfo(**r))
    return s.RotulosResponse(
        data=rows,
        meta=_meta(
            snap,
            extra_filters={
                "area": [a.value for a in area] if area else None,
                "ti": ti,
                "confianca": confianca,
                "q": q,
            },
            with_period=False,
        ),
    )


@router.get("/classification/changes", response_model=s.ChangesResponse, tags=["classificação"])
def classification_changes(snap: Snap) -> s.ChangesResponse:
    rows = []
    for r in _records(snap.mudancas):
        rows.append(
            s.MudancaCine(
                ano=r["ano"],
                rotulos_presentes=r["rotulos_presentes"],
                rotulos_novos=[x for x in (r["rotulos_novos"] or "").split(",") if x],
                rotulos_ausentes_vs_ano_anterior=[
                    x for x in (r["rotulos_ausentes_vs_ano_anterior"] or "").split(",") if x
                ],
            )
        )
    return s.ChangesResponse(
        data=rows,
        meta=_meta(
            snap, avisos=["O primeiro ano disponível não lista 'novos' (sem base de comparação)."]
        ),
    )


@router.get("/methodology", tags=["sistema"])
def methodology() -> dict:
    return methodology_document()
