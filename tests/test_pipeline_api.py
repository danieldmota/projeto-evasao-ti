"""Integração: ZIPs sintéticos → staging → warehouse → API."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from evasao_ti.acquisition.download import zip_path_for_year
from evasao_ti.api.app import create_app
from evasao_ti.storage.staging import ingest_year, list_staged_years
from evasao_ti.storage.warehouse import build_warehouse
from synthetic import default_rows


@pytest.fixture
def built(settings, synthetic_zip):
    """Anos 2021 e 2023 com dados FICTÍCIOS; 2022 e 2024 ausentes de propósito."""
    settings.raw_dir.mkdir(parents=True)
    for year, scale in ((2021, 1), (2023, 2)):
        src = synthetic_zip(year, rows=default_rows(year, scale=scale))
        shutil.copy(src, zip_path_for_year(settings.raw_dir, year))
        ingest_year(year, settings)
    build_warehouse(settings)
    return settings


@pytest.fixture
def client(built):
    return TestClient(create_app(built))


def test_ingest_is_idempotent(built) -> None:
    meta = ingest_year(2021, built)
    assert meta["status"] == "up_to_date"
    assert list_staged_years(built.staging_dir) == [2021, 2023]


def test_ingest_force_reprocesses(built) -> None:
    assert ingest_year(2021, built, force=True)["status"] == "processed"


def test_health(client) -> None:
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["anos_disponiveis"] == [2021, 2023]


def test_health_without_warehouse(settings) -> None:
    c = TestClient(create_app(settings))
    assert c.get("/api/v1/health").json()["status"] == "sem_dados"
    r = c.get("/api/v1/statistics/annual")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "dados_indisponiveis"


def test_years_lists_missing_years_without_zero(client) -> None:
    data = {d["ano"]: d for d in client.get("/api/v1/years").json()["data"]}
    assert data[2022]["status"] == "ausente"
    assert data[2024]["status"] == "ausente"
    assert data[2023]["md5_oficial_verificado"] is True


def test_annual_by_segment(client) -> None:
    r = client.get("/api/v1/statistics/annual", params={"group_by": "segmento"})
    assert r.status_code == 200
    body = r.json()
    rows = {(d["ano"], d["grupo_codigo"]): d for d in body["data"]}
    ti_2021 = rows[(2021, "TI")]
    # TI 2021 (fictício): presencial 100/25 + EaD 500/100; sequencial excluído
    assert ti_2021["matriculas"] == 600
    assert ti_2021["trancadas"] == 125
    assert ti_2021["taxa_trancamento"] == pytest.approx(125 / 725)
    # anos ausentes não viram zero
    assert not any(d["ano"] == 2022 for d in body["data"])
    assert body["meta"]["periodo"]["anos_ausentes"] == [2022, 2024]
    assert body["meta"]["fonte"]["instituicao"].startswith("Instituto Nacional")
    assert "Educação física" not in str(rows.get((2021, "EXATAS_EXCETO_TI"), ""))


def test_educacao_fisica_is_not_exatas(client) -> None:
    r = client.get("/api/v1/statistics/courses", params={"q": "educacao fisica"}).json()
    assert r["data"][0]["area"] == "NATUREZA_SAUDE"


def test_summary_pools_years(client) -> None:
    body = client.get("/api/v1/statistics/summary", params={"ti": True}).json()
    (ti,) = body["data"]
    # 2021: 600/125 ; 2023 (escala 2): 100*2 + 300*2 + 200*2 = 1200 / 25*2 + 90*2 + 10*2 = 250
    assert ti["matriculas"] == 600 + 1200
    assert ti["trancadas"] == 125 + 250
    assert ti["taxa_trancamento"] == pytest.approx(375 / (1800 + 375))
    assert any("vínculos-ano" in a for a in body["meta"]["avisos"])


def test_unclassified_are_reported_not_humanas(client) -> None:
    body = client.get("/api/v1/statistics/summary", params={"group_by": "area"}).json()
    codes = {d["grupo_codigo"] for d in body["data"]}
    assert "NAO_CLASSIFICADO" in codes
    assert any("Não classificado" in a for a in body["meta"]["avisos"])


def test_filters_modalidade_and_rede(client) -> None:
    ead = client.get(
        "/api/v1/statistics/summary", params={"ti": True, "modalidade": "ead", "year_end": 2021}
    ).json()
    assert ead["data"][0]["matriculas"] == 500
    pub = client.get(
        "/api/v1/statistics/summary", params={"rede": "publica", "group_by": "total"}
    ).json()
    assert pub["data"][0]["matriculas"] == 400 + 800  # só Educação física é pública


def test_courses_pagination_and_sorting(client) -> None:
    body = client.get(
        "/api/v1/statistics/courses", params={"limit": 2, "sort_by": "matriculas", "order": "desc"}
    ).json()
    assert body["meta"]["paginacao"]["total"] >= 6
    assert len(body["data"]) == 2
    assert body["data"][0]["matriculas"] >= body["data"][1]["matriculas"]
    assert body["data"][0]["codigos_cine"]


def test_validation_errors(client) -> None:
    r = client.get("/api/v1/statistics/annual", params={"year_start": 2024, "year_end": 2020})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "parametro_invalido"
    r = client.get("/api/v1/statistics/annual", params={"area": "HUMANAS_PADRAO"})
    assert r.status_code == 422
    r = client.get("/api/v1/statistics/courses", params={"sort_by": "drop table"})
    assert r.status_code == 422


def test_classification_endpoints(client) -> None:
    rot = client.get("/api/v1/classification/rotulos", params={"q": "sistemas"}).json()
    assert rot["data"][0]["is_ti"] is True
    assert rot["data"][0]["regra_codigo"] == "061"
    unk = client.get("/api/v1/classification/rotulos", params={"confianca": "nenhuma"}).json()
    assert {d["motivo"] for d in unk["data"]} == {"sem_regra"}
    ch = client.get("/api/v1/classification/changes").json()
    assert [d["ano"] for d in ch["data"]] == [2021, 2023]


def test_areas_and_methodology(client) -> None:
    areas = client.get("/api/v1/areas").json()
    assert {a["codigo"] for a in areas["data"]} >= {"TI", "EXATAS_TECNOLOGIA"}
    assert areas["regras"]
    m = client.get("/api/v1/methodology").json()
    assert "trancadas / (matriculas + trancadas)" in m["indicadores"]["taxa_trancamento"]["formula"]
    assert "evasao_desistencia" in m["conceitos"]


def test_cors_header(client) -> None:
    r = client.get("/api/v1/health", headers={"Origin": "http://testserver"})
    assert r.headers.get("access-control-allow-origin") == "http://testserver"
    r = client.get("/api/v1/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_openapi_documents_endpoints(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for p in (
        "/api/v1/health",
        "/api/v1/areas",
        "/api/v1/years",
        "/api/v1/statistics/annual",
        "/api/v1/statistics/summary",
        "/api/v1/statistics/courses",
        "/api/v1/methodology",
    ):
        assert p in paths


def test_api_does_not_download(client, monkeypatch) -> None:
    import httpx

    import evasao_ti.acquisition.download as dl

    def boom(*a, **k):
        raise AssertionError("A API não pode acessar a rede nem baixar microdados")

    # Transporte de rede real (o TestClient usa transporte próprio, em memória)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", boom)
    monkeypatch.setattr(dl, "download_year", boom)
    for path in (
        "/api/v1/statistics/annual",
        "/api/v1/statistics/summary",
        "/api/v1/statistics/courses",
        "/api/v1/years",
    ):
        assert client.get(path).status_code == 200
