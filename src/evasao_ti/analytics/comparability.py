"""Avaliação de comparabilidade entre anos.

Duas fontes de alertas:
1. **Automáticos** (recalculados a cada build): variável zerada num ano em que os demais anos
   têm valores; variação anual atípica (> ``ATYPICAL_CHANGE``) em trancadas/desvinculados;
   avisos de qualidade da ingestão.
2. **Curados**: observações feitas na auditoria dos arquivos oficiais (com evidência).

Alertas não removem dados: o ano continua disponível e o alerta acompanha a resposta da API.
"""

from __future__ import annotations

import itertools

import pandas as pd

ATYPICAL_CHANGE = 0.40
CHECK_FIELDS = ["matriculas", "trancadas", "desvinculados", "transferidos", "falecidos"]
TREND_FIELDS = ["trancadas", "desvinculados"]

CURATED_NOTES: dict[int, list[str]] = {
    2009: [
        "QT_SIT_TRANSFERIDO é zero em todos os cursos de 2009 (provável ausência de coleta); "
        "indicadores sobre o total de vínculos ficam subestimados no denominador.",
        "Trancadas (+49%) e desvinculados (+112%) saltam de 2009 para 2010; trate comparações "
        "com 2009 com cautela.",
    ],
    2013: [
        "TP_REDE vem vazio na maioria das linhas do CSV oficial; a rede foi derivada de "
        "TP_CATEGORIA_ADMINISTRATIVA (regra determinística verificada em 2012, 2014 e 2024).",
    ],
    2020: [
        "No CSV oficial a coluna se chama CO_CINE_ROTULO2 (tratada como CO_CINE_ROTULO). "
        "Ano marcado pela pandemia de COVID-19: o aumento de trancamentos é plausível como "
        "fenômeno real, não como erro de dados.",
    ],
    2024: [
        "Revisão da CINE Brasil: códigos da área 06 (TI) foram reorganizados (ex.: Sistemas de "
        "informação 0615S02 → 0613S01; Ciência da computação 0614C01 → 0613C01). Os nomes dos "
        "cursos se mantêm, e /statistics/courses agrega por nome para preservar a série.",
        "Quebra na série de TI: 'Engenharia de computação (DCN Computação)' (0616E01, 17.426 "
        "matrículas em 2023) e 'Sistemas embarcados' saíram da área 06 e foram para Engenharia "
        "(0714E04 / 0714S03). Em 2023 isso equivalia a ~2,4% das matrículas de TI.",
    ],
}


def automatic_flags(totals: pd.DataFrame) -> dict[int, list[str]]:
    """``totals``: uma linha por ano com colunas CHECK_FIELDS (graduação)."""
    flags: dict[int, list[str]] = {}
    t = totals.set_index("ano").sort_index()
    for col in CHECK_FIELDS:
        if col not in t:
            continue
        positive_elsewhere = (t[col].fillna(0) > 0).sum()
        for ano, v in t[col].items():
            if pd.isna(v):
                flags.setdefault(int(ano), []).append(f"{col}: sem informação no ano")
            elif v == 0 and positive_elsewhere >= 2:
                flags.setdefault(int(ano), []).append(
                    f"{col} = 0 no ano, mas positivo nos demais (provável ausência de coleta)"
                )
    years = list(t.index)
    for col in TREND_FIELDS:
        if col not in t:
            continue
        for prev, cur in itertools.pairwise(years):
            if cur != prev + 1:
                continue
            a, b = t.at[prev, col], t.at[cur, col]
            if pd.notna(a) and pd.notna(b) and a > 0:
                change = (b - a) / a
                if abs(change) > ATYPICAL_CHANGE:
                    flags.setdefault(int(cur), []).append(
                        f"{col}: variação atípica de {change:+.0%} em relação a {prev}"
                    )
    return flags


def comparability_status(auto: list[str], curated: list[str]) -> str:
    return "atencao" if (auto or curated) else "comparavel"
