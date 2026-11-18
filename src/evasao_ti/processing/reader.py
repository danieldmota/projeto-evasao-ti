"""Leitura eficiente e validada do CSV de cursos (direto do ZIP, sem extrair).

Decisões:
- lê apenas as colunas necessárias (``usecols`` por nome exato) e em blocos (``chunksize``),
  agregando cada bloco ao nível de curso para limitar memória (o CSV de 2023 tem ~390 MB e
  ~670 mil linhas, pois cursos EaD aparecem uma vez por município de oferta);
- converte contagens para inteiros anuláveis e **falha** se houver valor não numérico ou
  negativo (nada de ``errors="coerce"`` + ``fillna(0)`` silencioso);
- preserva nulos: no layout oficial, linhas EaD com ``TP_DIMENSAO=3`` trazem só ``QT_CURSO``
  (contagens de alunos nulas) e linhas por município trazem contagens de alunos com
  ``QT_CURSO`` nulo. Somar com ``min_count=1`` mantém "sem informação" ≠ zero;
- remove as aspas que o INEP adicionou em ``CO_CINE_ROTULO`` (Nota informativa de 01/11/2022).
"""

from __future__ import annotations

import codecs
import re
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import IO

import pandas as pd

from evasao_ti.acquisition.archive import ArchiveInfo, inspect_archive
from evasao_ti.logging_setup import get_logger
from evasao_ti.processing.schema import (
    ATTRIBUTE_COLUMNS,
    AUXILIARY_COLUMNS,
    CATEGORIA_TO_REDE,
    COUNT_COLUMNS,
    COUNT_FIELDS,
    DIMENSAO_EAD_SOMENTE_BRASIL,
    GROUP_KEYS,
    REQUIRED_COLUMNS,
    canonical,
)

log = get_logger("reader")

CINE_ROTULO_RE = r"^\d{4}[A-Z]\d{2}$"
_YEAR_IN_NAME = re.compile(r"(\d{4})")


class SchemaError(Exception):
    """Colunas obrigatórias ausentes ou estrutura incompatível."""


class DataValidationError(Exception):
    """Valores inválidos (não numéricos, negativos, ano divergente...)."""


@dataclass
class QualityReport:
    year: int
    source_file: str
    source_member: str | None
    encoding: str
    columns_total: int
    extra_columns: list[str]
    rows_read: int = 0
    rows_by_dimensao: dict[str, int] = field(default_factory=dict)
    rows_by_nivel: dict[str, int] = field(default_factory=dict)
    nulls_expected: dict[str, int] = field(default_factory=dict)
    nulls_unexpected: dict[str, int] = field(default_factory=dict)
    cine_missing_rows: int = 0
    cine_invalid_format: int = 0
    cine_hierarchy_mismatch: int = 0
    courses_with_inconsistent_attributes: int = 0
    tp_rede_derivada_de_categoria: int = 0
    tp_rede_conflitos_categoria: int = 0
    totals_graduacao: dict[str, int | None] = field(default_factory=dict)
    totals_sequencial: dict[str, int | None] = field(default_factory=dict)
    md5_verified: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def detect_encoding(sample: bytes) -> str:
    """UTF-8 se o trecho decodificar como UTF-8 e contiver não-ASCII; senão Latin-1.

    Todos os anos inspecionados (2009, 2016, 2023) são Latin-1.
    """
    try:
        codecs.getincrementaldecoder("utf-8")().decode(sample, final=False)
    except UnicodeDecodeError:
        return "latin1"
    return "utf-8" if any(b > 127 for b in sample) else "latin1"


@contextmanager
def _open_source(path: Path, member: str | None) -> Iterator[IO[bytes]]:
    if member is None:
        with path.open("rb") as f:
            yield f
    else:
        with zipfile.ZipFile(path) as zf, zf.open(member) as f:
            yield f


def read_header(path: Path, member: str | None) -> tuple[list[str], str]:
    with _open_source(path, member) as f:
        sample = f.read(1 << 20)
    encoding = detect_encoding(sample)
    first_line = sample.split(b"\n", 1)[0].decode(encoding).rstrip("\r")
    return [c.strip() for c in first_line.split(";")], encoding


def validate_header(raw_columns: list[str]) -> list[str]:
    """Retorna colunas extras; levanta SchemaError se faltar obrigatória ou houver duplicatas."""
    canon = [canonical(c) for c in raw_columns]
    dupes = sorted({c for c in canon if canon.count(c) > 1})
    if dupes:
        raise SchemaError(f"Colunas duplicadas no cabeçalho: {dupes}")
    missing = [c for c in REQUIRED_COLUMNS if c not in canon]
    if missing:
        raise SchemaError(f"Colunas obrigatórias ausentes: {missing}")
    return sorted(set(canon) - set(REQUIRED_COLUMNS))


def _to_counts(chunk: pd.DataFrame, offset: int) -> None:
    for col in COUNT_FIELDS:
        raw = chunk[col]
        num = pd.to_numeric(raw, errors="coerce")
        bad = raw.notna() & num.isna()
        if bad.any():
            idx = bad[bad].index[:5].tolist()
            examples = raw[bad].head(5).tolist()
            raise DataValidationError(
                f"Valores não numéricos em {col} (linhas ~{[i + offset for i in idx]}): {examples}"
            )
        if (num < 0).any():
            raise DataValidationError(f"Valores negativos em {col}")
        if (num.dropna() % 1 != 0).any():
            raise DataValidationError(f"Valores não inteiros em {col}")
        chunk[col] = num.astype("Int64")


def _derive_rede(chunk: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    """Preenche TP_REDE nulo a partir de TP_CATEGORIA_ADMINISTRATIVA (ver schema.py)."""
    expected = chunk["tp_categoria_administrativa"].map(CATEGORIA_TO_REDE)
    both = chunk["tp_rede"].notna() & expected.notna()
    report.tp_rede_conflitos_categoria += int((chunk.loc[both, "tp_rede"] != expected[both]).sum())
    fill = chunk["tp_rede"].isna() & expected.notna()
    if fill.any():
        chunk.loc[fill, "tp_rede"] = expected[fill]
        report.tp_rede_derivada_de_categoria += int(fill.sum())
    return chunk.drop(columns=list(AUXILIARY_COLUMNS.values()))


def _count(series: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in series.value_counts(dropna=False).items()}


def _merge_counts(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + v
    return out


def infer_year_from_name(path: Path) -> int | None:
    m = _YEAR_IN_NAME.findall(path.name)
    return int(m[-1]) if m else None


def read_cursos(
    path: Path,
    expected_year: int | None = None,
    *,
    chunksize: int = 200_000,
    verify_md5: bool = True,
) -> tuple[pd.DataFrame, QualityReport]:
    """Lê um ZIP oficial ou um CSV avulso e retorna (cursos agregados, relatório de qualidade).

    A saída tem uma linha por combinação de atributos do curso (normalmente uma por
    ``co_curso``), com as contagens somadas entre municípios/dimensões.
    """
    member: str | None = None
    archive: ArchiveInfo | None = None
    if path.suffix.lower() == ".zip":
        archive = inspect_archive(path, expected_year=expected_year, verify_md5=verify_md5)
        member = archive.member
        expected_year = expected_year or archive.year
    else:
        expected_year = expected_year or infer_year_from_name(path)
    if expected_year is None:
        raise DataValidationError(f"Não foi possível determinar o ano de {path}")

    raw_cols, encoding = read_header(path, member)
    extra = validate_header(raw_cols)
    usecols = [c for c in raw_cols if canonical(c) in REQUIRED_COLUMNS]

    rename = {**ATTRIBUTE_COLUMNS, **AUXILIARY_COLUMNS, **COUNT_COLUMNS}
    report = QualityReport(
        year=expected_year,
        source_file=str(path),
        source_member=member,
        encoding=encoding,
        columns_total=len(raw_cols),
        extra_columns=extra,
        md5_verified=bool(archive and archive.md5_verified),
    )

    partials: list[pd.DataFrame] = []
    offset = 0
    with _open_source(path, member) as f:
        reader = pd.read_csv(
            f,
            sep=";",
            encoding=encoding,
            usecols=usecols,
            dtype=str,
            keep_default_na=False,
            na_values=[""],
            chunksize=chunksize,
        )
        for chunk in reader:
            chunk.columns = [rename[canonical(c)] for c in chunk.columns]
            for col in [*GROUP_KEYS, "tp_dimensao", *AUXILIARY_COLUMNS.values()]:
                chunk[col] = chunk[col].str.strip().str.strip('"').str.strip()
                chunk.loc[chunk[col] == "", col] = pd.NA
            _to_counts(chunk, offset)
            chunk = _derive_rede(chunk, report)

            anos = set(chunk["ano"].dropna().unique())
            if anos != {str(expected_year)}:
                raise DataValidationError(
                    f"NU_ANO_CENSO divergente: esperado {expected_year}, encontrado {sorted(anos)}"
                )

            report.rows_read += len(chunk)
            report.rows_by_dimensao = _merge_counts(
                report.rows_by_dimensao, _count(chunk["tp_dimensao"])
            )
            report.rows_by_nivel = _merge_counts(
                report.rows_by_nivel, _count(chunk["tp_nivel_academico"])
            )
            dim3 = chunk["tp_dimensao"] == DIMENSAO_EAD_SOMENTE_BRASIL
            for col in COUNT_FIELDS:
                nulls = chunk[col].isna()
                # QT_CURSO só é informado nas linhas de dimensão 1 e 3; contagens de alunos
                # ficam nulas nas linhas de dimensão 3 (EaD somente nível Brasil).
                expected_mask = ~dim3 if col == "qt_cursos" else dim3
                expected_mask = expected_mask & (chunk["tp_dimensao"] != "1")
                exp = int((nulls & expected_mask).sum())
                unexp = int((nulls & ~expected_mask).sum())
                if exp:
                    report.nulls_expected[col] = report.nulls_expected.get(col, 0) + exp
                if unexp:
                    report.nulls_unexpected[col] = report.nulls_unexpected.get(col, 0) + unexp

            agg = chunk.groupby(GROUP_KEYS, dropna=False, sort=False)[COUNT_FIELDS].sum(min_count=1)
            agg["n_registros"] = chunk.groupby(GROUP_KEYS, dropna=False, sort=False).size()
            partials.append(agg)
            offset += len(chunk)

    if not partials:
        raise DataValidationError(f"Arquivo sem linhas de dados: {path}")

    combined = pd.concat(partials)
    sums = combined.groupby(level=list(range(len(GROUP_KEYS))), dropna=False)
    df = sums[COUNT_FIELDS].sum(min_count=1)
    df["n_registros"] = sums["n_registros"].sum()
    df = df.reset_index()
    df["ano"] = df["ano"].astype(int)
    for col in COUNT_FIELDS:
        df[col] = df[col].astype("Int64")

    _quality_checks(df, report)
    log.info(
        "CSV lido",
        extra={
            "ctx": {
                "ano": expected_year,
                "linhas": report.rows_read,
                "cursos": len(df),
                "md5_ok": report.md5_verified,
            }
        },
    )
    return df, report


def _totals(df: pd.DataFrame) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for col in COUNT_FIELDS:
        s = df[col].sum(min_count=1)
        out[col] = None if pd.isna(s) else int(s)
    return out


def _quality_checks(df: pd.DataFrame, report: QualityReport) -> None:
    rot = df["co_cine_rotulo"]
    report.cine_missing_rows = int(rot.isna().sum())
    valid = rot.dropna()
    report.cine_invalid_format = int((~valid.str.match(CINE_ROTULO_RE)).sum())
    has = df.dropna(
        subset=[
            "co_cine_rotulo",
            "co_cine_area_detalhada",
            "co_cine_area_especifica",
            "co_cine_area_geral",
        ]
    )
    mismatch = (
        (has["co_cine_rotulo"].str[:4] != has["co_cine_area_detalhada"])
        | (has["co_cine_area_detalhada"].str[:3] != has["co_cine_area_especifica"])
        | (has["co_cine_area_especifica"].str[:2] != has["co_cine_area_geral"])
    )
    report.cine_hierarchy_mismatch = int(mismatch.sum())
    report.courses_with_inconsistent_attributes = int(df["co_curso"].duplicated().sum())

    grad = df[df["tp_nivel_academico"] == "1"]
    seq = df[df["tp_nivel_academico"] == "2"]
    report.totals_graduacao = _totals(grad)
    report.totals_sequencial = _totals(seq)

    if report.nulls_unexpected:
        report.warnings.append(f"Nulos fora do padrão esperado: {report.nulls_unexpected}")
    if report.tp_rede_derivada_de_categoria:
        report.warnings.append(
            f"TP_REDE ausente em {report.tp_rede_derivada_de_categoria} linhas; derivado de "
            "TP_CATEGORIA_ADMINISTRATIVA (regra determinística validada em outros anos)"
        )
    if report.tp_rede_conflitos_categoria:
        report.warnings.append(
            f"{report.tp_rede_conflitos_categoria} linhas com TP_REDE divergente da categoria"
        )
    if df["tp_rede"].isna().any():
        report.warnings.append(f"{int(df['tp_rede'].isna().sum())} cursos sem rede identificável")
    if report.cine_missing_rows:
        report.warnings.append(f"{report.cine_missing_rows} cursos sem código CINE")
    if report.cine_invalid_format:
        report.warnings.append(f"{report.cine_invalid_format} códigos CINE com formato inválido")
    if report.cine_hierarchy_mismatch:
        report.warnings.append(
            f"{report.cine_hierarchy_mismatch} cursos com hierarquia CINE inconsistente"
        )
    if report.courses_with_inconsistent_attributes:
        report.warnings.append(
            f"{report.courses_with_inconsistent_attributes} códigos de curso com atributos "
            "divergentes entre linhas (mantidos separados; somas não são afetadas)"
        )
