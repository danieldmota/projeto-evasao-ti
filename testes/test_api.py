import pytest
from fastapi.testclient import TestClient

from evasao import api

cliente = TestClient(api.app)


def linhas(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_health(base_teste):
    corpo = cliente.get("/api/v1/health").json()
    assert corpo == {"status": "ok", "anos_disponiveis": [2021, 2023]}


def test_sem_base(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "BASE", tmp_path / "nao_existe.duckdb")
    assert cliente.get("/api/v1/health").json()["status"] == "sem_dados"
    r = cliente.get("/api/v1/statistics/annual")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "dados_indisponiveis"


def test_anos_ausentes_nao_viram_zero(base_teste):
    r = cliente.get("/api/v1/statistics/annual", params={"group_by": "segmento"})
    dados = {(d["ano"], d["grupo_codigo"]): d for d in linhas(r)}
    assert {ano for ano, _ in dados} == {2021, 2023}
    assert r.json()["meta"]["periodo"]["anos_ausentes"] == [2022, 2024]
    anos = {d["ano"]: d for d in linhas(cliente.get("/api/v1/years"))}
    assert anos[2022]["status"] == "ausente"
    assert anos[2023]["md5_verificado"] is True


def test_ti_por_ano_sem_sequencial(base_teste):
    r = cliente.get("/api/v1/statistics/annual", params={"group_by": "segmento"})
    ti = {d["ano"]: d for d in linhas(r) if d["grupo_codigo"] == "TI"}
    # 2021 (fictício): presencial 100/25 + EaD 500/100; o sequencial (999) fica de fora
    assert ti[2021]["matriculas"] == 600
    assert ti[2021]["trancadas"] == 125
    assert ti[2021]["taxa_trancamento"] == pytest.approx(125 / 725)


def test_consolidado_e_razao_de_somas(base_teste):
    r = cliente.get("/api/v1/statistics/summary", params={"group_by": "segmento", "ti": "true"})
    (ti,) = linhas(r)
    assert "ano" not in ti
    # 2021: 125/725; 2023 (escala 2): 250/1450 -> 375/2175 (média das taxas daria outro valor)
    assert ti["taxa_trancamento"] == pytest.approx(375 / 2175)
    avisos = " ".join(r.json()["meta"]["avisos"])
    assert "vínculos-ano" in avisos


def test_aviso_nao_classificado_em_portugues(base_teste):
    meta = cliente.get("/api/v1/statistics/summary").json()["meta"]
    assert any("das matrículas do recorte estão em cursos 'Não classificado'" in a
               and "," in a for a in meta["avisos"])
    assert meta["classificacao"]["versao_mapeamento"] == "1.1.0"


def test_filtros(base_teste):
    r = cliente.get("/api/v1/statistics/summary",
                    params={"group_by": "total", "modalidade": "ead", "year_start": 2021,
                            "year_end": 2021})
    (total,) = linhas(r)
    assert total["matriculas"] == 500
    r = cliente.get("/api/v1/statistics/summary",
                    params={"group_by": "area", "area": ["NATUREZA_SAUDE"], "rede": "publica"})
    (saude,) = linhas(r)
    assert saude["grupo_codigo"] == "NATUREZA_SAUDE"
    assert saude["matriculas"] == 400 + 800


def test_cursos(base_teste):
    r = cliente.get("/api/v1/statistics/courses", params={"q": "sistemas", "sort_by": "trancadas"})
    (curso,) = linhas(r)
    assert curso["no_cine_rotulo"] == "Sistemas de informação"
    assert curso["codigos_cine"] == ["0615S02"]
    assert curso["anos_com_dados"] == [2021, 2023]
    assert r.json()["meta"]["paginacao"] == {"total": 1, "limit": 50, "offset": 0}


@pytest.mark.parametrize(
    "params",
    [
        {"group_by": "xyz"},
        {"area": "INVENTADA"},
        {"year_start": 2024, "year_end": 2020},
        {"modalidade": "hibrido"},
    ],
)
def test_parametros_invalidos(base_teste, params):
    r = cliente.get("/api/v1/statistics/annual", params=params)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "parametro_invalido"


def test_rotulos_e_areas(base_teste):
    rot = linhas(cliente.get("/api/v1/classification/rotulos", params={"ti": "true"}))
    assert [r["co_cine_rotulo"] for r in rot] == ["0615S02"]
    areas = linhas(cliente.get("/api/v1/areas"))
    assert {a["codigo"] for a in areas} >= {"TI", "EXATAS_TECNOLOGIA", "NAO_CLASSIFICADO"}
    assert "limitacoes" in cliente.get("/api/v1/methodology").json()


def test_cors(base_teste):
    r = cliente.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    r = cliente.get("/api/v1/health", headers={"Origin": "http://site-estranho.com"})
    assert "access-control-allow-origin" not in r.headers
