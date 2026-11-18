"""Testes com os ZIPs reais do INEP (pulados se dados/brutos não tiver os arquivos)."""

import pytest

from evasao.config import caminho_zip
from evasao.processamento import ler_cursos

# 2023 confere com as publicações que citam o INEP; os demais são de regressão
MATRICULAS_GRADUACAO = {
    2009: 5_954_021,
    2013: 7_305_977,
    2020: 8_680_354,
    2023: 9_976_782,
    2024: 10_226_873,
}


def zip_real(ano):
    caminho = caminho_zip(ano)
    if not caminho.exists():
        pytest.skip(f"ZIP real de {ano} não encontrado")
    return caminho


@pytest.mark.parametrize("ano", sorted(MATRICULAS_GRADUACAO))
def test_totais_reais(ano):
    df, info = ler_cursos(zip_real(ano), ano)
    assert info["md5_ok"]
    graduacao = df[df["tp_nivel_academico"] == "1"]
    assert graduacao["matriculas"].sum() == MATRICULAS_GRADUACAO[ano]
    assert df["co_cine_rotulo"].notna().all()


def test_2023_com_sequenciais():
    df, _ = ler_cursos(zip_real(2023), 2023)
    assert df["matriculas"].sum() == 9_977_217
