"""Áreas do projeto (narrativa do site) e segmentos derivados.

As 4 áreas NÃO são uma classificação oficial; são um agrupamento do projeto construído sobre a
CINE Brasil por meio de ``data/cine_area_mapping.csv``. "TI" é definido de forma objetiva como a
área geral CINE 06 — "Computação e Tecnologias da Informação e Comunicação (TIC)".
"""

from __future__ import annotations

from enum import StrEnum


class Area(StrEnum):
    EXATAS_TECNOLOGIA = "EXATAS_TECNOLOGIA"
    NATUREZA_SAUDE = "NATUREZA_SAUDE"
    GESTAO_NEGOCIOS = "GESTAO_NEGOCIOS"
    HUMANAS_SOCIAIS_ARTES = "HUMANAS_SOCIAIS_ARTES"
    NAO_CLASSIFICADO = "NAO_CLASSIFICADO"


AREA_LABELS: dict[Area, str] = {
    Area.EXATAS_TECNOLOGIA: "Ciências Exatas e Tecnologia",
    Area.NATUREZA_SAUDE: "Ciências da Natureza e Saúde",
    Area.GESTAO_NEGOCIOS: "Gestão e Negócios",
    Area.HUMANAS_SOCIAIS_ARTES: "Ciências Humanas, Sociais e Artes",
    Area.NAO_CLASSIFICADO: "Não classificado",
}

AREA_ORDER: dict[Area, int] = {a: i for i, a in enumerate(Area, start=1)}


class Segmento(StrEnum):
    """Áreas com TI separada do restante de Exatas (para a comparação TI × demais)."""

    TI = "TI"
    EXATAS_EXCETO_TI = "EXATAS_EXCETO_TI"
    NATUREZA_SAUDE = "NATUREZA_SAUDE"
    GESTAO_NEGOCIOS = "GESTAO_NEGOCIOS"
    HUMANAS_SOCIAIS_ARTES = "HUMANAS_SOCIAIS_ARTES"
    NAO_CLASSIFICADO = "NAO_CLASSIFICADO"


SEGMENTO_LABELS: dict[Segmento, str] = {
    Segmento.TI: "Tecnologia da Informação (CINE 06)",
    Segmento.EXATAS_EXCETO_TI: "Ciências Exatas e Tecnologia (exceto TI)",
    Segmento.NATUREZA_SAUDE: AREA_LABELS[Area.NATUREZA_SAUDE],
    Segmento.GESTAO_NEGOCIOS: AREA_LABELS[Area.GESTAO_NEGOCIOS],
    Segmento.HUMANAS_SOCIAIS_ARTES: AREA_LABELS[Area.HUMANAS_SOCIAIS_ARTES],
    Segmento.NAO_CLASSIFICADO: AREA_LABELS[Area.NAO_CLASSIFICADO],
}

SEGMENTO_ORDER: dict[Segmento, int] = {s: i for i, s in enumerate(Segmento, start=1)}

TI_CINE_AREA_GERAL = "06"
TI_RULE = "CINE área geral 06 — Computação e Tecnologias da Informação e Comunicação (TIC)"


def segmento_for(area: Area | str, is_ti: bool) -> Segmento:
    if is_ti:
        return Segmento.TI
    area = Area(area)
    if area is Area.EXATAS_TECNOLOGIA:
        return Segmento.EXATAS_EXCETO_TI
    return Segmento(area.value)
