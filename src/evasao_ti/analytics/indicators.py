"""Definições e cálculo dos indicadores.

Unidade de contagem: **vínculo de aluno a curso no ano de referência** (não pessoa). Um mesmo
estudante pode ter vínculos em mais de um curso e aparece em todos os anos em que estiver
vinculado; os microdados públicos (agregados por curso, desde a reestruturação por LGPD) não
permitem identificar pessoas entre anos.

Indicadores (todos são razões de somas; agregações nunca fazem média de percentuais):

- ``taxa_trancamento`` = trancadas / (matriculas + trancadas)
  Proporção de vínculos com matrícula trancada entre os vínculos cursando, formados ou
  trancados. Como ``QT_MAT`` (Cursando + Formado) **não inclui** trancadas, somá-las no
  denominador é necessário para obter uma proporção ∈ [0, 1]. É o denominador usado pelo
  notebook, agora validado contra o dicionário oficial.
- ``participacao_trancadas_vinculos`` = trancadas / vinculos_total, onde
  vinculos_total = matriculas + trancadas + desvinculados + transferidos + falecidos.
- ``taxa_desvinculacao`` = desvinculados / vinculos_total. Indicador **complementar**;
  NÃO é a taxa oficial de evasão/desistência do INEP (que é calculada por coorte nos
  Indicadores de Fluxo da Educação Superior).

Taxa é ``None`` quando o denominador é zero ou desconhecido.
"""

from __future__ import annotations

import pandas as pd

COUNT_FIELDS_API = [
    "qt_cursos",
    "ingressantes",
    "matriculas",
    "concluintes",
    "trancadas",
    "desvinculados",
    "transferidos",
    "falecidos",
]

INDICATOR_DEFINITIONS: dict[str, dict[str, str]] = {
    "taxa_trancamento": {
        "formula": "trancadas / (matriculas + trancadas)",
        "descricao": (
            "Proporção de vínculos com matrícula trancada entre os vínculos cursando, formados "
            "ou trancados no ano de referência."
        ),
        "unidade": "proporção (0–1); multiplique por 100 para percentual",
    },
    "participacao_trancadas_vinculos": {
        "formula": "trancadas / (matriculas + trancadas + desvinculados + transferidos "
        "+ falecidos)",
        "descricao": "Participação das matrículas trancadas no total de vínculos declarados.",
        "unidade": "proporção (0–1)",
    },
    "taxa_desvinculacao": {
        "formula": "desvinculados / (matriculas + trancadas + desvinculados + transferidos "
        "+ falecidos)",
        "descricao": (
            "Participação de alunos desvinculados do curso no total de vínculos. Indicador "
            "complementar; não equivale à taxa oficial de evasão/desistência do INEP."
        ),
        "unidade": "proporção (0–1)",
    },
}


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    num = num.astype("Float64")
    den = den.astype("Float64")
    out = num / den
    return out.mask(den.isna() | (den == 0) | num.isna())


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona denominadores e taxas a um DataFrame já agregado (numeradores somados)."""
    out = df.copy()
    base = out["matriculas"].astype("Int64") + out["trancadas"].astype("Int64")
    vinc = (
        base
        + out["desvinculados"].astype("Int64")
        + out["transferidos"].astype("Int64")
        + out["falecidos"].astype("Int64")
    )
    out["denominador_trancamento"] = base
    out["vinculos_total"] = vinc
    out["taxa_trancamento"] = _ratio(out["trancadas"], base)
    out["participacao_trancadas_vinculos"] = _ratio(out["trancadas"], vinc)
    out["taxa_desvinculacao"] = _ratio(out["desvinculados"], vinc)
    return out


def aggregate(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Soma numeradores/denominadores por ``by`` e só então calcula as taxas.

    ``min_count=1``: um grupo sem nenhuma informação permanece nulo (não vira zero).
    """
    if df.empty:
        cols = by + COUNT_FIELDS_API
        return add_indicators(pd.DataFrame({c: pd.Series(dtype="Int64") for c in cols}))
    grouped = df.groupby(by, dropna=False, sort=True)[COUNT_FIELDS_API].sum(min_count=1)
    return add_indicators(grouped.reset_index())
