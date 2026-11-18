"""Consultas sobre a tabela de fatos (funções puras, testáveis sem API)."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

import pandas as pd

from evasao_ti.analytics.indicators import aggregate
from evasao_ti.classification.areas import AREA_LABELS, SEGMENTO_LABELS, Area, Segmento


class GroupBy(StrEnum):
    area = "area"
    segmento = "segmento"
    cine_geral = "cine_geral"
    total = "total"


class Modalidade(StrEnum):
    presencial = "presencial"
    ead = "ead"


class Rede(StrEnum):
    publica = "publica"
    privada = "privada"


@dataclass
class Filters:
    year_start: int | None = None
    year_end: int | None = None
    areas: list[Area] = field(default_factory=list)
    segmentos: list[Segmento] = field(default_factory=list)
    ti: bool | None = None
    modalidade: Modalidade | None = None
    rede: Rede | None = None
    cine_geral: list[str] = field(default_factory=list)
    rotulos: list[str] = field(default_factory=list)
    q: str | None = None

    def as_dict(self) -> dict:
        return {
            "year_start": self.year_start,
            "year_end": self.year_end,
            "area": [a.value for a in self.areas] or None,
            "segmento": [s.value for s in self.segmentos] or None,
            "ti": self.ti,
            "modalidade": self.modalidade.value if self.modalidade else None,
            "rede": self.rede.value if self.rede else None,
            "cine_geral": self.cine_geral or None,
            "rotulo": self.rotulos or None,
            "q": self.q,
        }


def normalize_text(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold().strip()


def apply_filters(fact: pd.DataFrame, f: Filters) -> pd.DataFrame:
    m = pd.Series(True, index=fact.index)
    if f.year_start is not None:
        m &= fact["ano"] >= f.year_start
    if f.year_end is not None:
        m &= fact["ano"] <= f.year_end
    if f.areas:
        m &= fact["area"].isin([a.value for a in f.areas])
    if f.segmentos:
        m &= fact["segmento"].isin([s.value for s in f.segmentos])
    if f.ti is not None:
        m &= fact["is_ti"] == f.ti
    if f.modalidade:
        m &= fact["modalidade"] == f.modalidade.value
    if f.rede:
        m &= fact["rede"] == f.rede.value
    if f.cine_geral:
        m &= fact["co_cine_area_geral"].isin(f.cine_geral)
    if f.rotulos:
        m &= fact["co_cine_rotulo"].isin(f.rotulos)
    if f.q:
        needle = normalize_text(f.q)
        names = fact["no_cine_rotulo"].fillna("").map(normalize_text)
        m &= names.str.contains(needle, regex=False)
    return fact[m]


def _group_columns(group_by: GroupBy) -> tuple[str, str]:
    return {
        GroupBy.area: ("area", "area"),
        GroupBy.segmento: ("segmento", "segmento"),
        GroupBy.cine_geral: ("co_cine_area_geral", "no_cine_area_geral"),
        GroupBy.total: ("_total", "_total"),
    }[group_by]


def _with_group(df: pd.DataFrame, group_by: GroupBy) -> pd.DataFrame:
    df = df.copy()
    if group_by is GroupBy.total:
        df["grupo_codigo"] = "TOTAL"
        df["grupo_nome"] = "Total (todas as áreas)"
    elif group_by is GroupBy.area:
        df["grupo_codigo"] = df["area"]
        df["grupo_nome"] = df["area"].map(lambda a: AREA_LABELS[Area(a)])
    elif group_by is GroupBy.segmento:
        df["grupo_codigo"] = df["segmento"]
        df["grupo_nome"] = df["segmento"].map(lambda s: SEGMENTO_LABELS[Segmento(s)])
    else:
        df["grupo_codigo"] = df["co_cine_area_geral"].fillna("SEM_CINE")
        df["grupo_nome"] = df["no_cine_area_geral"].fillna("Sem código CINE")
    return df


def annual(fact: pd.DataFrame, f: Filters, group_by: GroupBy) -> pd.DataFrame:
    df = _with_group(apply_filters(fact, f), group_by)
    return aggregate(df, ["ano", "grupo_codigo", "grupo_nome"])


def summary(fact: pd.DataFrame, f: Filters, group_by: GroupBy) -> tuple[pd.DataFrame, list[int]]:
    """Consolidado do período: soma numeradores e denominadores de todos os anos filtrados."""
    filtered = apply_filters(fact, f)
    years = sorted(int(y) for y in filtered["ano"].unique())
    df = _with_group(filtered, group_by)
    return aggregate(df, ["grupo_codigo", "grupo_nome"]), years


# Agrupa pelo NOME CINE do curso (e não pelo código): a revisão CINE de 2024 trocou códigos
# mantendo nomes (ex.: "Sistemas de informação" 0615S02 → 0613S01). Área/segmento entram na
# chave para que um curso que mudou de área (ex.: "Sistemas embarcados") apareça em linhas
# separadas, sem misturar classificações.
COURSE_KEYS = [
    "no_cine_rotulo",
    "area",
    "segmento",
    "is_ti",
    "co_cine_area_geral",
    "no_cine_area_geral",
]
_CONF_RANK = {"nenhuma": 0, "baixa": 1, "media": 2, "alta": 3}


def _sorted_unique(s: pd.Series) -> list:
    return sorted({x for x in s if pd.notna(x)})


def courses(fact: pd.DataFrame, f: Filters) -> pd.DataFrame:
    df = apply_filters(fact, f)
    out = aggregate(df, COURSE_KEYS)
    if df.empty:
        for col in ("codigos_cine", "areas_detalhadas", "regras", "anos_com_dados"):
            out[col] = pd.Series(dtype=object)
        out["confianca"] = pd.Series(dtype=object)
        return out
    work = df.assign(
        _det=df["co_cine_area_detalhada"].fillna("")
        + " - "
        + df["no_cine_area_detalhada"].fillna(""),
        _regra=df["regra_nivel"].fillna("nenhuma") + ":" + df["regra_codigo"].fillna("-"),
        _conf=df["confianca"].fillna("nenhuma").map(_CONF_RANK),
    )
    extra = (
        work.groupby(COURSE_KEYS, dropna=False)
        .agg(
            codigos_cine=("co_cine_rotulo", _sorted_unique),
            areas_detalhadas=("_det", _sorted_unique),
            regras=("_regra", _sorted_unique),
            _conf=("_conf", "min"),  # confiança mais conservadora entre os códigos
            anos_com_dados=("ano", lambda s: sorted(int(x) for x in s.unique())),
        )
        .reset_index()
    )
    inv = {v: k for k, v in _CONF_RANK.items()}
    extra["confianca"] = extra.pop("_conf").map(inv)
    return out.merge(extra, on=COURSE_KEYS, how="left", validate="one_to_one")
