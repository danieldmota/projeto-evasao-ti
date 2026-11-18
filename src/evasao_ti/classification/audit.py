"""Auditoria: compara a classificação CINE com o classificador por palavras-chave do notebook."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from evasao_ti.analytics.indicators import aggregate
from evasao_ti.classification.legacy import LEGACY_TO_AREA, classificar_area_legado
from evasao_ti.classification.mapping import classify_frame
from evasao_ti.processing.schema import NIVEL_GRADUACAO


def compare_with_legacy(cursos: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna (matriz área_legado × área_cine em matrículas, divergências por rótulo)."""
    df = cursos[cursos["tp_nivel_academico"] == NIVEL_GRADUACAO].copy()
    if "area" not in df.columns:
        df = classify_frame(df)
    names = df["no_curso"].drop_duplicates()
    legacy = {n: LEGACY_TO_AREA[classificar_area_legado(n)] for n in names}
    df["area_legado"] = df["no_curso"].map(legacy)
    df.loc[df["no_curso"].isna(), "area_legado"] = LEGACY_TO_AREA[classificar_area_legado(None)]

    matrix = df.pivot_table(
        index="area_legado", columns="area", values="matriculas", aggfunc="sum", fill_value=0
    ).astype("int64")
    diverg = (
        df[df["area_legado"] != df["area"]]
        .groupby(
            ["ano", "co_cine_rotulo", "no_cine_rotulo", "area_legado", "area", "confianca"],
            dropna=False,
        )["matriculas"]
        .sum(min_count=1)
        .reset_index()
        .sort_values("matriculas", ascending=False)
    )
    return matrix, diverg


def legacy_vs_new_rates(cursos: pd.DataFrame) -> pd.DataFrame:
    """Taxa por área: método do notebook (todos os níveis, palavras-chave) × novo (CINE)."""
    df = cursos.copy()
    if "area" not in df.columns:
        df = classify_frame(df)
    df["area_legado"] = df["no_curso"].map(lambda n: LEGACY_TO_AREA[classificar_area_legado(n)])
    old = aggregate(df, ["ano", "area_legado"]).rename(columns={"area_legado": "area_codigo"})
    old["metodo"] = "notebook (palavras-chave, graduação + sequencial)"
    new = aggregate(df[df["tp_nivel_academico"] == NIVEL_GRADUACAO], ["ano", "area"]).rename(
        columns={"area": "area_codigo"}
    )
    new["metodo"] = "novo (CINE, graduação)"
    cols = ["metodo", "ano", "area_codigo", "matriculas", "trancadas", "taxa_trancamento"]
    return pd.concat([old[cols], new[cols]], ignore_index=True)


def write_audit(cursos: pd.DataFrame, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix, diverg = compare_with_legacy(cursos)
    rates = legacy_vs_new_rates(cursos)
    paths = {
        "matriz": out_dir / "auditoria_matriz_legado_x_cine.csv",
        "divergencias": out_dir / "auditoria_divergencias_por_rotulo.csv",
        "taxas": out_dir / "auditoria_taxas_legado_x_novo.csv",
    }
    matrix.to_csv(paths["matriz"], encoding="utf-8")
    diverg.to_csv(paths["divergencias"], index=False, encoding="utf-8")
    rates.to_csv(paths["taxas"], index=False, encoding="utf-8")
    return paths
