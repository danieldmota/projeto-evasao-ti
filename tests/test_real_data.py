"""Testes com os ZIPs REAIS do INEP (pulados se data/raw não tiver os arquivos).

Valores de referência:
- 2023 graduação = 9.976.782 matrículas e 9.977.217 incluindo sequenciais — totais que
  aparecem em publicações que citam o INEP (conferido em 18/11/2026).
- Demais anos: valores calculados por este projeto na primeira execução completa
  (18/11/2026), usados como teste de regressão. Se o INEP republicar um ano, atualize aqui.
"""

from __future__ import annotations

import pytest

from conftest import REAL_RAW
from evasao_ti.processing.reader import read_cursos

REGRESSION_MATRICULAS_GRADUACAO = {
    2009: 5_954_021,
    2013: 7_305_977,
    2020: 8_680_354,
    2023: 9_976_782,
    2024: 10_226_873,
}


def _zip(year: int):
    p = REAL_RAW / f"microdados_censo_da_educacao_superior_{year}.zip"
    if not p.exists():
        pytest.skip(f"ZIP real de {year} ausente em {REAL_RAW}")
    return p


@pytest.mark.real_data
@pytest.mark.parametrize("year", sorted(REGRESSION_MATRICULAS_GRADUACAO))
def test_real_totals(year: int) -> None:
    _df, rep = read_cursos(_zip(year), expected_year=year)
    assert rep.md5_verified
    assert rep.totals_graduacao["matriculas"] == REGRESSION_MATRICULAS_GRADUACAO[year]
    assert rep.nulls_unexpected == {}
    assert rep.cine_missing_rows == 0


@pytest.mark.real_data
def test_real_2023_including_sequenciais() -> None:
    _, rep = read_cursos(_zip(2023), expected_year=2023)
    total = rep.totals_graduacao["matriculas"] + rep.totals_sequencial["matriculas"]
    assert total == 9_977_217
