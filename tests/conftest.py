from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from evasao_ti.config import Settings
from synthetic import default_rows, to_csv_bytes, write_zip

REAL_RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        expected_year_start=2021,
        expected_year_end=2024,
        log_format="text",
        cors_origins=["http://testserver"],
    )


@pytest.fixture
def synthetic_zip(tmp_path: Path):
    def _make(year: int = 2023, rows=None, **kw) -> Path:
        rows = rows if rows is not None else default_rows(year)
        target = tmp_path / f"microdados_censo_da_educacao_superior_{year}.zip"
        return write_zip(target, year, to_csv_bytes(rows), **kw)

    return _make
