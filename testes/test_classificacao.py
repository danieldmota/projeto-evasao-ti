import pytest

from evasao.classificacao import (
    AREAS,
    carregar_mapeamento,
    classificar,
    classificar_como_notebook,
)


@pytest.mark.parametrize(
    ("rotulo", "area", "segmento"),
    [
        ("0915E01", "NATUREZA_SAUDE", "NATUREZA_SAUDE"),  # Educação física (notebook: Exatas)
        ("0615S02", "EXATAS_TECNOLOGIA", "TI"),  # Sistemas de informação
        ("0613S01", "EXATAS_TECNOLOGIA", "TI"),  # Sistemas de informação (CINE 2024)
        ("0714E04", "EXATAS_TECNOLOGIA", "EXATAS_EXCETO_TI"),  # Eng. de computação (Engenharia)
        ("0114M01", "HUMANAS_SOCIAIS_ARTES", "HUMANAS_SOCIAIS_ARTES"),  # Licenciatura matemática
        ("0311E01", "GESTAO_NEGOCIOS", "GESTAO_NEGOCIOS"),  # Economia (decisão do projeto)
        ("0421D01", "HUMANAS_SOCIAIS_ARTES", "HUMANAS_SOCIAIS_ARTES"),  # Direito
        ("0811A01", "NATUREZA_SAUDE", "NATUREZA_SAUDE"),  # Agronomia (notebook: Humanas)
        ("0011A06", "NAO_CLASSIFICADO", "NAO_CLASSIFICADO"),  # ABI Computação
    ],
)
def test_cursos_conhecidos(rotulo, area, segmento):
    c = classificar(rotulo)
    assert c["area"] == area
    assert c["segmento"] == segmento


def test_regra_mais_especifica_vence():
    assert classificar("0311E01")["regra_nivel"] == "detalhada"
    assert classificar("0615S02")["regra_nivel"] == "especifica"


@pytest.mark.parametrize("rotulo", ["9999X99", "0922X01"])
def test_codigo_sem_regra_nao_vira_humanas(rotulo):
    assert classificar(rotulo)["area"] == "NAO_CLASSIFICADO"


@pytest.mark.parametrize("rotulo", [None, "", '""', "ABC"])
def test_sem_codigo_ou_invalido(rotulo):
    assert classificar(rotulo)["area"] == "NAO_CLASSIFICADO"


def test_aspas_no_codigo():
    assert classificar('"0615S02"')["is_ti"]


def test_mapeamento_integro():
    regras = carregar_mapeamento()
    assert len(regras) > 40
    assert {r["area"] for r in regras.values()} <= set(AREAS)
    assert all(r["justificativa"].strip() for r in regras.values())


def test_mapeamento_cobre_todas_as_areas_especificas_observadas():
    # áreas específicas CINE que aparecem nos CSVs reais 2009-2024
    observadas = ["001", "011", "018", "019", "021", "022", "023", "028", "032", "038", "039",
                  "041", "042", "048", "049", "051", "052", "053", "054", "058", "061", "068",
                  "071", "072", "073", "078", "081", "082", "083", "084", "088", "091", "098"]
    for codigo in observadas:
        assert classificar(codigo + "0X01")["regra_codigo"] is not None, codigo


def test_classificador_do_notebook_reproduz_os_erros():
    assert classificar_como_notebook("EDUCAÇÃO FÍSICA") == "EXATAS_TECNOLOGIA"
    assert classificar_como_notebook("AGRONOMIA") == "HUMANAS_SOCIAIS_ARTES"
    assert classificar_como_notebook(None) == "HUMANAS_SOCIAIS_ARTES"
    assert classificar_como_notebook("ADMINISTRAÇÃO") == "GESTAO_NEGOCIOS"
