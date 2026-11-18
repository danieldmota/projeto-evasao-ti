"""Indicadores: razão de somas, nulos ≠ zero, denominador validado."""

from __future__ import annotations

import pandas as pd
import pytest

from evasao_ti.analytics.comparability import automatic_flags
from evasao_ti.analytics.indicators import COUNT_FIELDS_API, add_indicators, aggregate


def frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for c in COUNT_FIELDS_API:
        if c not in df:
            df[c] = 0
        df[c] = df[c].astype("Int64")
    return df


def test_rate_formula_uses_matriculas_plus_trancadas() -> None:
    df = add_indicators(frame([{"matriculas": 80, "trancadas": 20, "desvinculados": 50}]))
    assert df.loc[0, "denominador_trancamento"] == 100
    assert df.loc[0, "taxa_trancamento"] == pytest.approx(0.20)
    assert df.loc[0, "vinculos_total"] == 150
    assert df.loc[0, "taxa_desvinculacao"] == pytest.approx(50 / 150)


def test_aggregation_is_ratio_of_sums_not_mean_of_rates() -> None:
    df = frame(
        [
            {"g": "A", "matriculas": 9, "trancadas": 1},  # 10%
            {"g": "A", "matriculas": 450, "trancadas": 50},  # 10%
            {"g": "B", "matriculas": 1, "trancadas": 1},  # 50% com peso pequeno
            {"g": "B", "matriculas": 990, "trancadas": 10},  # 1% com peso grande
        ]
    )
    out = aggregate(df, ["g"]).set_index("g")
    assert out.loc["B", "taxa_trancamento"] == pytest.approx(11 / 1002)
    mean_of_rates = (0.5 + 0.01) / 2
    assert out.loc["B", "taxa_trancamento"] != pytest.approx(mean_of_rates)


def test_zero_denominator_gives_null_rate() -> None:
    df = add_indicators(frame([{"matriculas": 0, "trancadas": 0}]))
    assert pd.isna(df.loc[0, "taxa_trancamento"])


def test_missing_information_is_not_zero() -> None:
    df = frame([{"g": "A", "matriculas": 10, "trancadas": 1}])
    df = pd.concat([df, frame([{"g": "B"}])], ignore_index=True)
    df.loc[1, ["matriculas", "trancadas"]] = pd.NA
    out = aggregate(df, ["g"]).set_index("g")
    assert pd.isna(out.loc["B", "matriculas"])
    assert pd.isna(out.loc["B", "taxa_trancamento"])


def test_aggregate_does_not_invent_missing_years() -> None:
    df = frame([{"ano": 2020, "matriculas": 10}, {"ano": 2022, "matriculas": 12}])
    out = aggregate(df, ["ano"])
    assert out["ano"].tolist() == [2020, 2022]


def test_automatic_flags_detect_zeroed_column_and_jumps() -> None:
    t = pd.DataFrame(
        {
            "ano": [2009, 2010, 2011],
            "matriculas": [100, 110, 120],
            "trancadas": [10, 20, 21],
            "desvinculados": [5, 5, 5],
            "transferidos": [0, 3, 4],
            "falecidos": [1, 1, 1],
        }
    )
    flags = automatic_flags(t)
    assert any("transferidos = 0" in f for f in flags[2009])
    assert any("trancadas" in f and "+100%" in f for f in flags[2010])
    assert 2011 not in flags
