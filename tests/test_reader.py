"""Leitura/validação do CSV de cursos com fixtures sintéticas."""

from __future__ import annotations

import pytest

from evasao_ti.acquisition.archive import ArchiveError, inspect_archive
from evasao_ti.processing.reader import (
    DataValidationError,
    SchemaError,
    detect_encoding,
    read_cursos,
)
from synthetic import HEADER, default_rows, row, to_csv_bytes, write_zip


def test_reads_zip_and_aggregates_ead_rows(synthetic_zip) -> None:
    df, rep = read_cursos(synthetic_zip(2023))
    assert rep.md5_verified
    assert rep.rows_read == 10
    ead = df[df["co_curso"] == "2"].iloc[0]
    # duas linhas por município somadas; linha nível Brasil contribui só com QT_CURSO
    assert ead["matriculas"] == 500
    assert ead["trancadas"] == 100
    assert ead["qt_cursos"] == 1
    assert ead["n_registros"] == 3
    assert rep.nulls_unexpected == {}
    assert rep.nulls_expected["matriculas"] == 1
    assert rep.totals_graduacao["matriculas"] == 100 + 500 + 400 + 1000 + 50 + 500 + 10
    assert rep.totals_sequencial["matriculas"] == 999


def test_cine_quotes_are_removed(synthetic_zip) -> None:
    df, rep = read_cursos(synthetic_zip(2023))
    assert set(df["co_cine_rotulo"]) >= {"0615S02", "0915E01"}
    assert rep.cine_invalid_format == 0
    assert rep.cine_hierarchy_mismatch == 0


def test_column_order_and_extra_columns_do_not_matter(tmp_path) -> None:
    header = [*list(reversed(HEADER)), "IN_COMUNITARIA", "IN_CONFESSIONAL"]
    rows = [{**r, "IN_COMUNITARIA": 0, "IN_CONFESSIONAL": 0} for r in default_rows(2023)]
    z = write_zip(tmp_path / "x.zip", 2023, to_csv_bytes(rows, header))
    df, rep = read_cursos(z)
    assert rep.extra_columns[-2:] == ["IN_COMUNITARIA", "IN_CONFESSIONAL"] or set(
        rep.extra_columns
    ) >= {"IN_COMUNITARIA", "IN_CONFESSIONAL"}
    assert df["matriculas"].sum() > 0


def test_2020_alias_co_cine_rotulo2(tmp_path) -> None:
    header = ["CO_CINE_ROTULO2" if c == "CO_CINE_ROTULO" else c for c in HEADER]
    rows = [{**r, "CO_CINE_ROTULO2": r["CO_CINE_ROTULO"]} for r in default_rows(2020)]
    z = write_zip(tmp_path / "x.zip", 2020, to_csv_bytes(rows, header))
    df, _ = read_cursos(z)
    assert "0615S02" in set(df["co_cine_rotulo"])


def test_missing_required_column_fails_explicitly(tmp_path) -> None:
    header = [c for c in HEADER if c != "QT_SIT_TRANCADA"]
    z = write_zip(tmp_path / "x.zip", 2023, to_csv_bytes(default_rows(2023), header))
    with pytest.raises(SchemaError, match="QT_SIT_TRANCADA"):
        read_cursos(z)


def test_no_partial_column_matching(tmp_path) -> None:
    # Uma coluna "QT_MAT_FEM" não pode substituir "QT_MAT" (erro do notebook: busca parcial)
    header = [c for c in HEADER if c != "QT_MAT"]
    z = write_zip(tmp_path / "x.zip", 2023, to_csv_bytes(default_rows(2023), header))
    with pytest.raises(SchemaError, match="QT_MAT"):
        read_cursos(z)


def test_non_numeric_count_fails(tmp_path) -> None:
    rows = default_rows(2023)
    rows[0]["QT_MAT"] = "abc"
    z = write_zip(tmp_path / "x.zip", 2023, to_csv_bytes(rows))
    with pytest.raises(DataValidationError, match="não numéricos"):
        read_cursos(z)


def test_negative_count_fails(tmp_path) -> None:
    rows = default_rows(2023)
    rows[0]["QT_SIT_TRANCADA"] = -1
    z = write_zip(tmp_path / "x.zip", 2023, to_csv_bytes(rows))
    with pytest.raises(DataValidationError, match="negativos"):
        read_cursos(z)


def test_year_mismatch_fails(tmp_path) -> None:
    z = write_zip(tmp_path / "x.zip", 2023, to_csv_bytes(default_rows(2022)))
    with pytest.raises(DataValidationError, match="NU_ANO_CENSO"):
        read_cursos(z)


def test_unexpected_nulls_are_reported(tmp_path) -> None:
    rows = default_rows(2023)
    rows[0]["QT_SIT_TRANCADA"] = ""  # presencial (dimensão 1) sem valor: inesperado
    z = write_zip(tmp_path / "x.zip", 2023, to_csv_bytes(rows))
    _, rep = read_cursos(z)
    assert rep.nulls_unexpected == {"trancadas": 1}
    assert rep.warnings


def test_rede_derived_from_categoria_when_missing(tmp_path) -> None:
    rows = [
        row(2013, 1, "A", "0732E01", rede="", categoria=1, mat=10),
        row(2013, 2, "B", "0732E01", rede="", categoria=5, mat=10),
        row(2013, 3, "C", "0732E01", rede=2, categoria=4, mat=10),
    ]
    z = write_zip(tmp_path / "x.zip", 2013, to_csv_bytes(rows))
    df, rep = read_cursos(z)
    assert df.set_index("co_curso")["tp_rede"].to_dict() == {"1": "1", "2": "2", "3": "2"}
    assert rep.tp_rede_derivada_de_categoria == 2
    assert rep.tp_rede_conflitos_categoria == 0


def test_plain_csv_input(tmp_path) -> None:
    p = tmp_path / "MICRODADOS_CADASTRO_CURSOS_2023.CSV"
    p.write_bytes(to_csv_bytes(default_rows(2023)))
    df, rep = read_cursos(p)
    assert rep.year == 2023 and rep.source_member is None
    assert len(df) > 0


def test_chunked_reading_gives_same_result(synthetic_zip) -> None:
    z = synthetic_zip(2023)
    a, _ = read_cursos(z)
    b, _ = read_cursos(z, chunksize=2)
    key = ["co_curso", "tp_nivel_academico"]
    pd_a = a.sort_values(key).reset_index(drop=True)
    pd_b = b.sort_values(key).reset_index(drop=True)
    assert pd_a["matriculas"].tolist() == pd_b["matriculas"].tolist()
    assert pd_a["qt_cursos"].tolist() == pd_b["qt_cursos"].tolist()


def test_detect_encoding() -> None:
    assert detect_encoding("Educação".encode("latin1")) == "latin1"
    assert detect_encoding("Educação".encode()) == "utf-8"
    assert detect_encoding(b"ascii only") == "latin1"


# ------------------------------------------------------------------ ZIP


def test_md5_mismatch_is_detected(synthetic_zip) -> None:
    with pytest.raises(ArchiveError, match="MD5"):
        inspect_archive(synthetic_zip(2023, wrong_md5=True))


def test_truncated_zip_is_detected(synthetic_zip, tmp_path) -> None:
    z = synthetic_zip(2023)
    data = z.read_bytes()
    bad = tmp_path / "bad.zip"
    bad.write_bytes(data[: len(data) // 2])
    with pytest.raises(ArchiveError):
        inspect_archive(bad)


def test_member_found_in_any_root_folder(synthetic_zip) -> None:
    info = inspect_archive(synthetic_zip(2023, root="microdados_censo_da_educacao_superior_2023"))
    assert info.member.endswith("MICRODADOS_CADASTRO_CURSOS_2023.CSV")
    assert info.md5_verified


def test_wrong_year_zip_rejected(synthetic_zip) -> None:
    with pytest.raises(ArchiveError, match="2022"):
        inspect_archive(synthetic_zip(2023), expected_year=2022)


def test_zip_without_md5_is_accepted_but_not_verified(synthetic_zip) -> None:
    info = inspect_archive(synthetic_zip(2023, with_md5=False))
    assert info.md5_verified is False
