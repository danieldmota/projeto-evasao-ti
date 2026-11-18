"""Classificação por código CINE com regra rastreável.

Ordem de resolução (do mais específico ao mais geral):
``rotulo`` (7 caracteres) → ``detalhada`` (4) → ``especifica`` (3) → ``geral`` (2).
A primeira regra encontrada define a área. Se nenhuma regra existir, ou se o curso não tiver
código CINE válido, o resultado é ``NAO_CLASSIFICADO`` — **nunca** uma área padrão.

Cada resultado registra o nível e o código da regra aplicada, a confiança e a justificativa,
permitindo auditar por que um curso foi para determinada área.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

import pandas as pd

from evasao_ti.classification.areas import (
    TI_CINE_AREA_GERAL,
    Area,
    segmento_for,
)

# Incrementar a cada alteração em data/cine_area_mapping.csv e registrar em docs/METODOLOGIA.md
MAPPING_VERSION = "1.1.0"
MAPPING_FILE = "cine_area_mapping.csv"

LEVELS: tuple[str, ...] = ("rotulo", "detalhada", "especifica", "geral")
LEVEL_LENGTH = {"rotulo": 7, "detalhada": 4, "especifica": 3, "geral": 2}
CONFIDENCES = {"alta", "media", "baixa"}
_CODE_RE = {
    "rotulo": re.compile(r"^\d{4}[A-Z]\d{2}$"),
    "detalhada": re.compile(r"^\d{4}$"),
    "especifica": re.compile(r"^\d{3}$"),
    "geral": re.compile(r"^\d{2}$"),
}


class MappingError(Exception):
    pass


@dataclass(frozen=True)
class Rule:
    nivel: str
    codigo: str
    descricao_cine: str
    area: Area
    confianca: str
    justificativa: str


@dataclass(frozen=True)
class Classification:
    area: Area
    is_ti: bool
    segmento: str
    regra_nivel: str | None
    regra_codigo: str | None
    confianca: str
    justificativa: str
    motivo: str  # "regra_cine" | "cine_ausente" | "cine_invalido" | "sem_regra"


@dataclass(frozen=True)
class Mapping:
    version: str
    sha256: str
    rules: dict[tuple[str, str], Rule]

    def classify(
        self,
        rotulo: str | None,
        detalhada: str | None = None,
        especifica: str | None = None,
        geral: str | None = None,
    ) -> Classification:
        rotulo = _clean(rotulo)
        # Deriva níveis superiores do rótulo quando não informados explicitamente
        if rotulo and _CODE_RE["rotulo"].match(rotulo):
            detalhada = _clean(detalhada) or rotulo[:4]
            especifica = _clean(especifica) or rotulo[:3]
            geral = _clean(geral) or rotulo[:2]
        else:
            detalhada, especifica, geral = _clean(detalhada), _clean(especifica), _clean(geral)

        codes = {"rotulo": rotulo, "detalhada": detalhada, "especifica": especifica, "geral": geral}
        if not any(codes.values()):
            return _unclassified("cine_ausente", "Curso sem código CINE nos microdados")
        invalid = [lvl for lvl, c in codes.items() if c and not _CODE_RE[lvl].match(c)]
        if invalid:
            return _unclassified(
                "cine_invalido", f"Código CINE com formato inválido no(s) nível(is) {invalid}"
            )

        is_ti = geral == TI_CINE_AREA_GERAL
        for lvl in LEVELS:
            code = codes[lvl]
            if code and (lvl, code) in self.rules:
                r = self.rules[(lvl, code)]
                return Classification(
                    area=r.area,
                    is_ti=is_ti,
                    segmento=segmento_for(r.area, is_ti).value,
                    regra_nivel=lvl,
                    regra_codigo=code,
                    confianca=r.confianca,
                    justificativa=r.justificativa,
                    motivo="regra_cine",
                )
        result = _unclassified(
            "sem_regra", f"Nenhuma regra de correspondência para CINE {rotulo or detalhada}"
        )
        # TI continua identificável mesmo sem regra de área
        return Classification(**{**result.__dict__, "is_ti": is_ti})


def _clean(code: str | None) -> str | None:
    if code is None or (isinstance(code, float) and pd.isna(code)) or code is pd.NA:
        return None
    s = str(code).strip().strip('"').strip()
    return s or None


def _unclassified(motivo: str, msg: str) -> Classification:
    return Classification(
        area=Area.NAO_CLASSIFICADO,
        is_ti=False,
        segmento=Area.NAO_CLASSIFICADO.value,
        regra_nivel=None,
        regra_codigo=None,
        confianca="nenhuma",
        justificativa=msg,
        motivo=motivo,
    )


def parse_mapping(text: str, version: str = MAPPING_VERSION) -> Mapping:
    rules: dict[tuple[str, str], Rule] = {}
    reader = csv.DictReader(text.splitlines())
    expected = {"nivel", "codigo", "descricao_cine", "area", "confianca", "justificativa"}
    if set(reader.fieldnames or []) != expected:
        raise MappingError(f"Cabeçalho inválido: {reader.fieldnames}; esperado {sorted(expected)}")
    for i, row in enumerate(reader, start=2):
        nivel, codigo = row["nivel"].strip(), row["codigo"].strip()
        if nivel not in LEVELS:
            raise MappingError(f"Linha {i}: nível inválido {nivel!r}")
        if not _CODE_RE[nivel].match(codigo):
            raise MappingError(f"Linha {i}: código {codigo!r} inválido para nível {nivel}")
        try:
            area = Area(row["area"].strip())
        except ValueError as exc:
            raise MappingError(f"Linha {i}: área inválida {row['area']!r}") from exc
        conf = row["confianca"].strip()
        if conf not in CONFIDENCES:
            raise MappingError(f"Linha {i}: confiança inválida {conf!r}")
        if not row["justificativa"].strip():
            raise MappingError(f"Linha {i}: justificativa obrigatória")
        key = (nivel, codigo)
        if key in rules:
            raise MappingError(f"Linha {i}: regra duplicada {key}")
        rules[key] = Rule(
            nivel, codigo, row["descricao_cine"].strip(), area, conf, row["justificativa"].strip()
        )
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Mapping(version=version, sha256=sha, rules=rules)


@lru_cache
def load_mapping() -> Mapping:
    text = (
        resources.files("evasao_ti.classification")
        .joinpath("data", MAPPING_FILE)
        .read_text(encoding="utf-8")
    )
    return parse_mapping(text)


CLASSIFICATION_COLUMNS = [
    "area",
    "is_ti",
    "segmento",
    "regra_nivel",
    "regra_codigo",
    "confianca",
    "justificativa",
    "motivo",
]


def classify_frame(df: pd.DataFrame, mapping: Mapping | None = None) -> pd.DataFrame:
    """Adiciona colunas de classificação a um DataFrame com colunas co_cine_*.

    Classifica apenas as combinações únicas de códigos (centenas), depois faz merge.
    """
    mapping = mapping or load_mapping()
    keys = [
        "co_cine_rotulo",
        "co_cine_area_detalhada",
        "co_cine_area_especifica",
        "co_cine_area_geral",
    ]
    uniq = df[keys].drop_duplicates()
    rows = []
    for rec in uniq.itertuples(index=False):
        c = mapping.classify(*rec)
        rows.append(
            [
                *rec,
                c.area.value,
                c.is_ti,
                c.segmento,
                c.regra_nivel,
                c.regra_codigo,
                c.confianca,
                c.justificativa,
                c.motivo,
            ]
        )
    lookup = pd.DataFrame(rows, columns=keys + CLASSIFICATION_COLUMNS)
    return df.merge(lookup, on=keys, how="left", validate="many_to_one")
