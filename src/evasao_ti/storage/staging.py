"""Staging: um Parquet padronizado por ano + metadados de proveniência.

Permite atualizar um único ano sem reprocessar o histórico: cada ano é independente e só é
reprocessado se o arquivo de origem (SHA-256) ou a versão do schema de staging mudarem.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from evasao_ti import __version__
from evasao_ti.acquisition.archive import sha256_of_file
from evasao_ti.acquisition.download import load_manifest, zip_path_for_year
from evasao_ti.config import Settings
from evasao_ti.logging_setup import get_logger
from evasao_ti.processing.reader import read_cursos
from evasao_ti.processing.schema import STAGING_SCHEMA_VERSION

log = get_logger("staging")


def parquet_path(staging_dir: Path, year: int) -> Path:
    return staging_dir / f"cursos_{year}.parquet"


def meta_path(staging_dir: Path, year: int) -> Path:
    return staging_dir / f"cursos_{year}.meta.json"


def load_meta(staging_dir: Path, year: int) -> dict | None:
    p = meta_path(staging_dir, year)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def list_staged_years(staging_dir: Path) -> list[int]:
    years = []
    for p in staging_dir.glob("cursos_*.meta.json"):
        try:
            years.append(int(p.name.split("_")[1].split(".")[0]))
        except ValueError:
            continue
    return sorted(y for y in years if parquet_path(staging_dir, y).exists())


def ingest_file(
    source: Path,
    settings: Settings,
    *,
    year: int | None = None,
    force: bool = False,
    download_record: dict | None = None,
) -> dict:
    """Processa um ZIP/CSV e grava staging. Retorna os metadados gravados."""
    staging = settings.staging_dir
    staging.mkdir(parents=True, exist_ok=True)

    source_sha = (download_record or {}).get("sha256") or sha256_of_file(source)

    if year is not None and not force:
        previous = load_meta(staging, year)
        if (
            previous
            and previous.get("source_sha256") == source_sha
            and previous.get("staging_schema_version") == STAGING_SCHEMA_VERSION
            and parquet_path(staging, year).exists()
        ):
            log.info("ingestão ignorada: staging já atualizado", extra={"ctx": {"ano": year}})
            return {**previous, "status": "up_to_date"}

    df, report = read_cursos(source, expected_year=year)
    year = report.year

    out = parquet_path(staging, year)
    tmp = out.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, out)

    meta = {
        "year": year,
        "status": "processed",
        "source_file": source.name,
        "source_sha256": source_sha,
        "source_url": (download_record or {}).get("url"),
        "source_last_modified": (download_record or {}).get("last_modified"),
        "source_etag": (download_record or {}).get("etag"),
        "processed_at": datetime.now(UTC).isoformat(),
        "code_version": __version__,
        "staging_schema_version": STAGING_SCHEMA_VERSION,
        "rows_out": len(df),
        "quality": report.to_dict(),
    }
    mp = meta_path(staging, year)
    mp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(
        "staging gravado",
        extra={"ctx": {"ano": year, "arquivo": str(out), "avisos": len(report.warnings)}},
    )
    return meta


def ingest_year(year: int, settings: Settings, *, force: bool = False) -> dict:
    """Processa o ZIP oficial já baixado em raw/ para o ano informado."""
    zip_path = zip_path_for_year(settings.raw_dir, year)
    if not zip_path.exists():
        raise FileNotFoundError(
            f"ZIP de {year} não encontrado em {zip_path}. Rode 'evasao-ti download --years {year}'."
        )
    record = load_manifest(settings.raw_dir).get(str(year))
    return ingest_file(zip_path, settings, year=year, force=force, download_record=record)


def read_staged(staging_dir: Path, years: list[int] | None = None) -> pd.DataFrame:
    years = years or list_staged_years(staging_dir)
    frames = [pd.read_parquet(parquet_path(staging_dir, y)) for y in years]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
