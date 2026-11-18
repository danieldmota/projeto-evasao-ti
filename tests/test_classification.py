"""Classificação CINE: casos ambíguos, interdisciplinares, desconhecidos e TI."""

from __future__ import annotations

import pandas as pd
import pytest

from evasao_ti.classification.areas import Area, Segmento, segmento_for
from evasao_ti.classification.legacy import EXATAS, HUMANAS, classificar_area_legado
from evasao_ti.classification.mapping import (
    MappingError,
    classify_frame,
    load_mapping,
    parse_mapping,
)

M = load_mapping()


@pytest.mark.parametrize(
    ("rotulo", "area", "is_ti"),
    [
        ("0615S02", Area.EXATAS_TECNOLOGIA, True),  # Sistemas de informação (inclui ADS)
        ("0613S01", Area.EXATAS_TECNOLOGIA, True),  # Sistemas de informação (CINE 2024)
        ("0614C01", Area.EXATAS_TECNOLOGIA, True),  # Ciência da computação
        ("0616E01", Area.EXATAS_TECNOLOGIA, True),  # Eng. de computação (DCN Computação)
        ("0681C01", Area.EXATAS_TECNOLOGIA, True),  # Ciência de dados (CINE 2024)
        ("0714E04", Area.EXATAS_TECNOLOGIA, False),  # Eng. de computação (DCN Engenharia)
        ("0732E01", Area.EXATAS_TECNOLOGIA, False),  # Engenharia civil
        ("0533F01", Area.EXATAS_TECNOLOGIA, False),  # Física (bacharelado)
        ("0542E01", Area.EXATAS_TECNOLOGIA, False),  # Estatística (notebook: Humanas)
        ("0915E01", Area.NATUREZA_SAUDE, False),  # Educação física (notebook: Exatas!)
        ("0914R01", Area.NATUREZA_SAUDE, False),  # Radiologia (notebook: Humanas)
        ("0511B01", Area.NATUREZA_SAUDE, False),  # Biologia
        ("0811A01", Area.NATUREZA_SAUDE, False),  # Agronomia (notebook: Humanas)
        ("0311E01", Area.GESTAO_NEGOCIOS, False),  # Economia (decisão documentada)
        ("0413A01", Area.GESTAO_NEGOCIOS, False),  # Administração
        ("1015T01", Area.GESTAO_NEGOCIOS, False),  # Turismo
        ("0421D01", Area.HUMANAS_SOCIAIS_ARTES, False),  # Direito (CINE: área 04)
        ("0923S01", Area.HUMANAS_SOCIAIS_ARTES, False),  # Serviço social (CINE: área 09)
        ("0113P01", Area.HUMANAS_SOCIAIS_ARTES, False),  # Pedagogia
    ],
)
def test_known_courses(rotulo: str, area: Area, is_ti: bool) -> None:
    c = M.classify(rotulo)
    assert c.area is area
    assert c.is_ti is is_ti
    assert c.motivo == "regra_cine"
    assert c.regra_codigo is not None and rotulo.startswith(c.regra_codigo)


def test_teacher_training_follows_cine_education_not_content() -> None:
    # Licenciaturas em Física/Matemática/Computação: CINE área 01 (Educação)
    for rotulo in ("0114F02", "0114M01", "0114C05"):
        c = M.classify(rotulo)
        assert c.area is Area.HUMANAS_SOCIAIS_ARTES
        assert c.is_ti is False


def test_basic_entry_area_is_unclassified_not_humanas() -> None:
    c = M.classify("0011A06")  # ABI Computação
    assert c.area is Area.NAO_CLASSIFICADO
    assert c.regra_codigo == "001"


@pytest.mark.parametrize("rotulo", ["9999X99", "0922X01"])
def test_unknown_code_is_unclassified(rotulo: str) -> None:
    c = M.classify(rotulo)
    assert c.area is Area.NAO_CLASSIFICADO
    assert c.motivo == "sem_regra"
    assert c.area is not Area.HUMANAS_SOCIAIS_ARTES


@pytest.mark.parametrize("rotulo", [None, "", '""', float("nan"), pd.NA])
def test_missing_code_is_unclassified(rotulo: object) -> None:
    c = M.classify(rotulo)  # type: ignore[arg-type]
    assert c.area is Area.NAO_CLASSIFICADO
    assert c.motivo == "cine_ausente"


def test_invalid_code_is_unclassified() -> None:
    c = M.classify("ABC")
    assert c.area is Area.NAO_CLASSIFICADO
    assert c.motivo == "cine_invalido"


def test_quoted_code_is_accepted() -> None:
    assert M.classify('"0615S02"').is_ti


def test_ti_detectable_even_without_area_rule() -> None:
    c = M.classify("0699X01")  # área geral 06, específica 069 sem regra
    assert c.is_ti is True
    assert c.area is Area.NAO_CLASSIFICADO


def test_most_specific_rule_wins() -> None:
    # 0311 (Economia, detalhada) prevalece sobre a ausência de regra na específica 031
    assert M.classify("0311E01").regra_nivel == "detalhada"
    assert M.classify("0313P01").area is Area.HUMANAS_SOCIAIS_ARTES


def test_segments() -> None:
    assert segmento_for(Area.EXATAS_TECNOLOGIA, True) is Segmento.TI
    assert segmento_for(Area.EXATAS_TECNOLOGIA, False) is Segmento.EXATAS_EXCETO_TI
    assert segmento_for(Area.NATUREZA_SAUDE, False) is Segmento.NATUREZA_SAUDE


# Áreas específicas CINE observadas nos CSVs reais 2009–2024 (inventário da auditoria)
OBSERVED_ESPECIFICAS = [
    "001",
    "011",
    "018",
    "019",
    "021",
    "022",
    "023",
    "028",
    "031",
    "032",
    "038",
    "039",
    "041",
    "042",
    "048",
    "049",
    "051",
    "052",
    "053",
    "054",
    "058",
    "061",
    "068",
    "071",
    "072",
    "073",
    "078",
    "081",
    "082",
    "083",
    "084",
    "088",
    "091",
    "092",
    "098",
    "101",
    "102",
    "103",
    "104",
    "108",
]
OBSERVED_DETALHADAS_SEM_ESPECIFICA = [
    "0311",
    "0312",
    "0313",
    "0921",
    "0923",
    "1011",
    "1012",
    "1013",
    "1014",
    "1015",
    "1022",
    "1031",
    "1032",
    "1041",
]


def test_every_observed_cine_area_has_a_rule() -> None:
    for e in OBSERVED_ESPECIFICAS:
        if e in {"031", "092", "101", "102", "103", "104"}:
            continue  # resolvidas por regras de nível detalhado
        assert ("especifica", e) in M.rules, e
    for d in OBSERVED_DETALHADAS_SEM_ESPECIFICA:
        assert ("detalhada", d) in M.rules, d


def test_mapping_file_integrity() -> None:
    assert M.version
    assert len(M.sha256) == 64
    assert all(r.justificativa for r in M.rules.values())


def test_parse_mapping_rejects_bad_rows() -> None:
    header = "nivel,codigo,descricao_cine,area,confianca,justificativa\n"
    with pytest.raises(MappingError):
        parse_mapping(header + "especifica,061,x,HUMANAS_PADRAO,alta,j\n")
    with pytest.raises(MappingError):
        parse_mapping(header + "especifica,61,x,EXATAS_TECNOLOGIA,alta,j\n")
    with pytest.raises(MappingError):
        parse_mapping(header + "especifica,061,x,EXATAS_TECNOLOGIA,alta,\n")
    with pytest.raises(MappingError):
        parse_mapping(header + "especifica,061,x,EXATAS_TECNOLOGIA,alta,j\n" * 2)


def test_classify_frame_merges_without_duplicating_rows() -> None:
    df = pd.DataFrame(
        {
            "co_cine_rotulo": ["0615S02", "0615S02", "0915E01", None],
            "co_cine_area_detalhada": ["0615", "0615", "0915", None],
            "co_cine_area_especifica": ["061", "061", "091", None],
            "co_cine_area_geral": ["06", "06", "09", None],
            "matriculas": [1, 2, 3, 4],
        }
    )
    out = classify_frame(df)
    assert len(out) == 4
    assert out["area"].tolist() == [
        "EXATAS_TECNOLOGIA",
        "EXATAS_TECNOLOGIA",
        "NATUREZA_SAUDE",
        "NAO_CLASSIFICADO",
    ]


def test_legacy_classifier_bugs_are_documented() -> None:
    """O classificador do notebook manda Educação Física para Exatas e Agronomia para Humanas."""
    assert classificar_area_legado("EDUCAÇÃO FÍSICA") == EXATAS
    assert classificar_area_legado("AGRONOMIA") == HUMANAS
    assert classificar_area_legado("CIÊNCIAS BIOLÓGICAS") == HUMANAS
    assert classificar_area_legado(None) == HUMANAS
