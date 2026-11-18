"""Metodologia estruturada (servida em /api/v1/methodology e referenciada nas respostas)."""

from __future__ import annotations

from evasao_ti.analytics.indicators import INDICATOR_DEFINITIONS
from evasao_ti.classification.areas import TI_RULE
from evasao_ti.classification.mapping import MAPPING_VERSION

SOURCE = {
    "nome": "Microdados do Censo da Educação Superior",
    "instituicao": "Instituto Nacional de Estudos e Pesquisas Educacionais Anísio Teixeira (INEP)",
    "url": (
        "https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/"
        "censo-da-educacao-superior"
    ),
    "arquivo": "MICRODADOS_CADASTRO_CURSOS_AAAA.CSV (dentro do ZIP anual)",
    "classificacao": "CINE Brasil (https://www.gov.br/inep/pt-br/areas-de-atuacao/"
    "pesquisas-estatisticas-e-indicadores/cine-brasil)",
    "nota": (
        "Estatísticas calculadas por este projeto a partir dos microdados públicos. "
        "Não são estatísticas oficiais publicadas pelo INEP."
    ),
}

UNIT = (
    "Vínculos de aluno a curso de graduação no ano de referência (não pessoas). Taxas são "
    "proporções de 0 a 1."
)

SCOPE = (
    "Cursos de graduação (TP_NIVEL_ACADEMICO = 1), presenciais e a distância, todas as redes. "
    "Cursos sequenciais de formação específica são excluídos."
)

VARIABLES = {
    "matriculas": {
        "coluna_inep": "QT_MAT",
        "definicao_oficial": "Soma do número de alunos com situação de vínculo ao curso igual a "
        "Cursando e/ou Formado (Dicionário de Dados INEP).",
    },
    "trancadas": {
        "coluna_inep": "QT_SIT_TRANCADA",
        "definicao_oficial": "Quantidade de alunos com situação de vínculo no curso - matrícula "
        "trancada.",
    },
    "desvinculados": {
        "coluna_inep": "QT_SIT_DESVINCULADO",
        "definicao_oficial": "Quantidade de alunos com situação de vínculo no curso - aluno "
        "desvinculado do curso.",
    },
    "transferidos": {
        "coluna_inep": "QT_SIT_TRANSFERIDO",
        "definicao_oficial": "Aluno transferido para outro curso da mesma IES.",
    },
    "falecidos": {"coluna_inep": "QT_SIT_FALECIDO", "definicao_oficial": "Aluno falecido."},
    "concluintes": {"coluna_inep": "QT_CONC", "definicao_oficial": "Quantidade de concluintes."},
    "ingressantes": {
        "coluna_inep": "QT_ING",
        "definicao_oficial": "Cálculo de ingressantes: soma do número de alunos com data de "
        "ingresso de 01 de janeiro e 01 de julho do ano de referência do censo (texto literal "
        "do Dicionário de Dados INEP).",
    },
    "qt_cursos": {"coluna_inep": "QT_CURSO", "definicao_oficial": "Número de cursos."},
}

CONCEPTS = {
    "trancamento": "Situação de vínculo declarada pela IES: o aluno mantém o vínculo, mas "
    "suspendeu temporariamente os estudos. É medido diretamente (QT_SIT_TRANCADA).",
    "matricula": "No Censo, 'matrícula' = vínculos Cursando ou Formado no ano (QT_MAT). Não "
    "inclui trancados, desvinculados, transferidos nem falecidos.",
    "desvinculacao": "Situação de vínculo 'desvinculado do curso' (QT_SIT_DESVINCULADO). É o "
    "mais próximo de saída do curso disponível neste arquivo, mas não distingue abandono, "
    "desistência formal, jubilamento etc.",
    "evasao_desistencia": "Evasão/desistência exige acompanhar o mesmo aluno ao longo dos anos "
    "(coorte). O INEP publica isso nos 'Indicadores de Fluxo da Educação Superior' "
    "(taxa de desistência acumulada). Os microdados agregados por curso não permitem esse "
    "cálculo; este projeto NÃO calcula taxa de evasão.",
    "abandono": "Não há variável de abandono no arquivo de cursos.",
}

LIMITATIONS = [
    "Contagens são de vínculos-ano, não de pessoas: o mesmo estudante aparece em todos os anos "
    "em que estiver vinculado. Somas de vários anos ('consolidado do período') medem "
    "vínculos-ano, não 'pessoas que trancaram'.",
    "QT_MAT inclui formados no ano; a taxa de trancamento usa um denominador que mistura alunos "
    "cursando, formados e trancados.",
    "As 4 áreas do projeto são uma correspondência própria sobre a CINE (versionada), não uma "
    "classificação oficial. Rótulos com confiança 'baixa' e 'Não classificado' são informados.",
    "A CINE classifica licenciaturas (inclusive Matemática, Física e Computação) em Educação, "
    "portanto elas entram em Humanas e não em Exatas/TI.",
    "Anos ausentes não são preenchidos com zero; aparecem em 'anos_ausentes'.",
    "A série 2009–2020 foi republicada pelo INEP em 04/11/2022 no layout atual, com CINE "
    "atribuída retroativamente; alterações de códigos CINE entre anos são listadas em "
    "/api/v1/classification/changes.",
    "A seção 'TI' segue a CINE área geral 06; cursos tecnológicos com nome de TI mas outro "
    "código CINE (ex.: engenharia de computação na DCN de Engenharia) não entram em TI.",
]

AGGREGATION = (
    "Todas as agregações (por área, período ou curso) somam numeradores e denominadores e só "
    "então calculam a taxa (razão de somas). Nunca é feita média simples de percentuais."
)


def methodology_document() -> dict:
    return {
        "fonte": SOURCE,
        "unidade": UNIT,
        "escopo": SCOPE,
        "variaveis": VARIABLES,
        "conceitos": CONCEPTS,
        "indicadores": INDICATOR_DEFINITIONS,
        "agregacao": AGGREGATION,
        "classificacao": {
            "versao_mapeamento": MAPPING_VERSION,
            "ordem_resolucao": ["rotulo", "detalhada", "especifica", "geral"],
            "regra_ti": TI_RULE,
            "sem_regra": "Cursos sem código CINE válido ou sem regra → 'Não classificado' "
            "(nunca uma área padrão).",
        },
        "limitacoes": LIMITATIONS,
        "aviso_orientacao_vocacional": (
            "O teste vocacional da plataforma é uma ferramenta de orientação e não constitui "
            "diagnóstico psicológico validado."
        ),
    }
