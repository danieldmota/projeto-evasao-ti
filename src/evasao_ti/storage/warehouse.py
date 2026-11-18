"""Construção do warehouse DuckDB a partir do staging.

O build é rápido (segundos) e determinístico: lê os Parquets anuais, aplica a classificação
vigente e grava um novo arquivo ``evasao_ti.duckdb`` de forma atômica. Alterar a tabela de
correspondência exige apenas ``evasao-ti build`` (sem reler os CSVs).

Tabelas:
- ``cursos``        — cursos padronizados por ano (graduação e sequenciais), classificados;
- ``fact_rotulo``   — graduação agregada por ano × rótulo CINE × modalidade × rede (base da API);
- ``anos``          — status, proveniência e qualidade de cada ano esperado;
- ``rotulos``       — classificação de cada rótulo CINE e anos em que aparece;
- ``cine_mudancas`` — códigos CINE que surgem/deixam de aparecer em cada ano;
- ``build_info``    — versão do código, do mapeamento e data do build.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from evasao_ti import __version__
from evasao_ti.analytics.comparability import (
    CURATED_NOTES,
    automatic_flags,
    comparability_status,
)
from evasao_ti.classification.mapping import classify_frame, load_mapping
from evasao_ti.config import Settings
from evasao_ti.logging_setup import get_logger
from evasao_ti.processing.schema import MODALIDADES, NIVEL_GRADUACAO, REDES
from evasao_ti.storage.staging import list_staged_years, load_meta, read_staged

log = get_logger("warehouse")


class WarehouseError(Exception):
    pass


FACT_DIMENSIONS = [
    "ano",
    "co_cine_rotulo",
    "no_cine_rotulo",
    "co_cine_area_geral",
    "no_cine_area_geral",
    "co_cine_area_especifica",
    "no_cine_area_especifica",
    "co_cine_area_detalhada",
    "no_cine_area_detalhada",
    "area",
    "segmento",
    "is_ti",
    "regra_nivel",
    "regra_codigo",
    "confianca",
    "modalidade",
    "rede",
]
COUNTS = [
    "qt_cursos",
    "ingressantes",
    "matriculas",
    "concluintes",
    "trancadas",
    "desvinculados",
    "transferidos",
    "falecidos",
]


def _years_table(settings: Settings, staged: list[int], fact: pd.DataFrame) -> pd.DataFrame:
    totals = fact.groupby("ano")[COUNTS].sum(min_count=1).reset_index()
    auto = automatic_flags(totals)
    rows = []
    all_years = sorted(set(settings.expected_years) | set(staged))
    for y in all_years:
        meta = load_meta(settings.staging_dir, y) if y in staged else None
        q = (meta or {}).get("quality", {})
        a_flags = auto.get(y, []) if meta else []
        c_notes = CURATED_NOTES.get(y, []) if meta else []
        rows.append(
            {
                "ano": y,
                "status": "disponivel" if meta else "ausente",
                "comparabilidade": comparability_status(a_flags, c_notes) if meta else None,
                "alertas_automaticos": json.dumps(a_flags, ensure_ascii=False),
                "notas_curadas": json.dumps(c_notes, ensure_ascii=False),
                "esperado": y in settings.expected_years,
                "arquivo_fonte": (meta or {}).get("source_file"),
                "url_fonte": (meta or {}).get("source_url"),
                "fonte_last_modified": (meta or {}).get("source_last_modified"),
                "fonte_sha256": (meta or {}).get("source_sha256"),
                "md5_oficial_verificado": q.get("md5_verified"),
                "processado_em": (meta or {}).get("processed_at"),
                "linhas_lidas": q.get("rows_read"),
                "avisos": json.dumps(q.get("warnings", []), ensure_ascii=False),
                "qualidade": json.dumps(q, ensure_ascii=False) if q else None,
            }
        )
    return pd.DataFrame(rows)


def _rotulos_table(cursos: pd.DataFrame) -> pd.DataFrame:
    g = cursos[cursos["tp_nivel_academico"] == NIVEL_GRADUACAO]
    grp = g.groupby("co_cine_rotulo", dropna=False)
    out = grp.agg(
        no_cine_rotulo=("no_cine_rotulo", "last"),
        nomes_distintos=("no_cine_rotulo", "nunique"),
        co_cine_area_geral=("co_cine_area_geral", "last"),
        no_cine_area_geral=("no_cine_area_geral", "last"),
        co_cine_area_especifica=("co_cine_area_especifica", "last"),
        co_cine_area_detalhada=("co_cine_area_detalhada", "last"),
        no_cine_area_detalhada=("no_cine_area_detalhada", "last"),
        area=("area", "last"),
        segmento=("segmento", "last"),
        is_ti=("is_ti", "last"),
        regra_nivel=("regra_nivel", "last"),
        regra_codigo=("regra_codigo", "last"),
        confianca=("confianca", "last"),
        justificativa=("justificativa", "last"),
        motivo=("motivo", "last"),
        primeiro_ano=("ano", "min"),
        ultimo_ano=("ano", "max"),
        anos=("ano", lambda s: ",".join(str(x) for x in sorted(s.unique()))),
    ).reset_index()
    return out


def _cine_changes(cursos: pd.DataFrame) -> pd.DataFrame:
    g = cursos[cursos["tp_nivel_academico"] == NIVEL_GRADUACAO]
    by_year = g.groupby("ano")["co_cine_rotulo"].apply(lambda s: set(s.dropna())).sort_index()
    rows, seen = [], set()
    prev: set[str] | None = None
    for ano, codes in by_year.items():
        novos = sorted(codes - seen) if prev is not None else []
        sumidos = sorted(prev - codes) if prev is not None else []
        rows.append(
            {
                "ano": int(ano),
                "rotulos_presentes": len(codes),
                "rotulos_novos": ",".join(novos),
                "rotulos_ausentes_vs_ano_anterior": ",".join(sumidos),
            }
        )
        seen |= codes
        prev = codes
    return pd.DataFrame(rows)


def build_warehouse(settings: Settings) -> dict:
    staged = list_staged_years(settings.staging_dir)
    if not staged:
        raise WarehouseError(
            "Nenhum ano no staging. Rode 'evasao-ti ingest' ou 'evasao-ti ingest-csv' antes."
        )
    mapping = load_mapping()
    cursos = read_staged(settings.staging_dir, staged)
    cursos = classify_frame(cursos, mapping)
    cursos["modalidade"] = cursos["tp_modalidade_ensino"].map(MODALIDADES).fillna("nao_informado")
    cursos["rede"] = cursos["tp_rede"].map(REDES).fillna("nao_informado")

    grad = cursos[cursos["tp_nivel_academico"] == NIVEL_GRADUACAO]
    grouped = grad.groupby(FACT_DIMENSIONS, dropna=False)
    fact = grouped[COUNTS].sum(min_count=1)
    fact["n_cursos_registros"] = grouped.size()  # alinhado pelo índice do grupo
    fact = fact.reset_index()

    anos = _years_table(settings, staged, fact)
    rotulos = _rotulos_table(cursos)
    mudancas = _cine_changes(cursos)
    info = {
        "built_at": datetime.now(UTC).isoformat(),
        "code_version": __version__,
        "mapping_version": mapping.version,
        "mapping_sha256": mapping.sha256,
        "years_available": staged,
        "years_expected": settings.expected_years,
        "scope": "graduação (TP_NIVEL_ACADEMICO = 1); sequenciais excluídos das estatísticas",
    }
    build_df = pd.DataFrame(
        [{"key": k, "value": json.dumps(v, ensure_ascii=False)} for k, v in info.items()]
    )

    target = settings.warehouse_path
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".duckdb.tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        for name, frame in {
            "cursos": cursos,
            "fact_rotulo": fact,
            "anos": anos,
            "rotulos": rotulos,
            "cine_mudancas": mudancas,
            "build_info": build_df,
        }.items():
            con.register("_tmp_df", frame)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM _tmp_df")
            con.unregister("_tmp_df")
        con.execute("CHECKPOINT")
    finally:
        con.close()
    _atomic_replace(tmp, target)
    log.info(
        "warehouse construído",
        extra={"ctx": {"arquivo": str(target), "anos": staged, "linhas_fato": len(fact)}},
    )
    return info


def _atomic_replace(tmp: Path, target: Path) -> None:
    try:
        os.replace(tmp, target)
    except PermissionError as exc:  # Windows: arquivo aberto pela API
        raise WarehouseError(
            f"Não foi possível substituir {target}: arquivo em uso (pare a API e rode de novo)."
        ) from exc
