"""Schema explícito do MICRODADOS_CADASTRO_CURSOS_AAAA.CSV.

Fonte das definições: ANEXO I - Dicionário de Dados (``dicionário_dados_educação_superior.xlsx``)
incluso em cada ZIP oficial. Trechos relevantes (aba ``cadastro_cursos``):

- ``QT_MAT``: "Cálculo de matrículas: soma do número de alunos com situação de vínculo ao curso
  igual a: Cursando e/ou Formado".
- ``QT_SIT_TRANCADA``: "Quantidade de alunos com situação de vínculo no curso - matrícula trancada".
- ``QT_SIT_DESVINCULADO``: "... aluno desvinculado do curso".
- ``QT_SIT_TRANSFERIDO``: "... aluno transferido para outro curso da mesma IES".
- ``QT_SIT_FALECIDO``: "... aluno falecido".
- ``TP_NIVEL_ACADEMICO``: 1. Graduação; 2. Sequencial de Formação Específica.
- ``TP_MODALIDADE_ENSINO``: 1. Presencial; 2. Curso a distância.
- ``TP_DIMENSAO`` (Nota informativa INEP, 01/11/2022): 1. presencial no Brasil;
  2. EaD no Brasil (por município); 3. EaD com dados somente a nível Brasil;
  4. EaD ofertado por IES brasileiras no exterior.

As colunas são selecionadas por **nome exato** (após remover espaços/aspas e converter para
maiúsculas). Não há correspondência parcial. Se uma coluna obrigatória faltar, o processamento
do ano falha com erro explícito. Renomeações futuras devem ser declaradas em
``COLUMN_ALIASES`` (vazio até hoje: os anos 2009, 2016 e 2023 inspecionados usam os mesmos
nomes; 2023 traz IN_COMUNITARIA/IN_CONFESSIONAL extras e outra ordem de colunas).
"""

from __future__ import annotations

# Incrementar quando o formato do staging mudar (força reprocessamento)
STAGING_SCHEMA_VERSION = 3

# nome no INEP -> nome padronizado
ATTRIBUTE_COLUMNS: dict[str, str] = {
    "NU_ANO_CENSO": "ano",
    "CO_IES": "co_ies",
    "CO_CURSO": "co_curso",
    "NO_CURSO": "no_curso",
    "TP_NIVEL_ACADEMICO": "tp_nivel_academico",
    "TP_MODALIDADE_ENSINO": "tp_modalidade_ensino",
    "TP_GRAU_ACADEMICO": "tp_grau_academico",
    "TP_REDE": "tp_rede",
    "TP_DIMENSAO": "tp_dimensao",
    "CO_CINE_ROTULO": "co_cine_rotulo",
    "NO_CINE_ROTULO": "no_cine_rotulo",
    "CO_CINE_AREA_GERAL": "co_cine_area_geral",
    "NO_CINE_AREA_GERAL": "no_cine_area_geral",
    "CO_CINE_AREA_ESPECIFICA": "co_cine_area_especifica",
    "NO_CINE_AREA_ESPECIFICA": "no_cine_area_especifica",
    "CO_CINE_AREA_DETALHADA": "co_cine_area_detalhada",
    "NO_CINE_AREA_DETALHADA": "no_cine_area_detalhada",
}

COUNT_COLUMNS: dict[str, str] = {
    "QT_CURSO": "qt_cursos",
    "QT_ING": "ingressantes",
    "QT_MAT": "matriculas",
    "QT_CONC": "concluintes",
    "QT_SIT_TRANCADA": "trancadas",
    "QT_SIT_DESVINCULADO": "desvinculados",
    "QT_SIT_TRANSFERIDO": "transferidos",
    "QT_SIT_FALECIDO": "falecidos",
}

# Colunas auxiliares: lidas para validação/derivação, não vão para o staging
AUXILIARY_COLUMNS: dict[str, str] = {
    "TP_CATEGORIA_ADMINISTRATIVA": "tp_categoria_administrativa",
}

REQUIRED_COLUMNS: tuple[str, ...] = (*ATTRIBUTE_COLUMNS, *AUXILIARY_COLUMNS, *COUNT_COLUMNS)

# Renomeações observadas nos arquivos oficiais: {"NOME_NO_ARQUIVO": "NOME_CANONICO"}.
# - 2020: o CSV oficial traz "CO_CINE_ROTULO2" no lugar de "CO_CINE_ROTULO" (mesmo conteúdo e
#   formato, ex.: "0413A02"). A detecção de colunas duplicadas impede que as duas coexistam.
COLUMN_ALIASES: dict[str, str] = {"CO_CINE_ROTULO2": "CO_CINE_ROTULO"}

# TP_REDE vazio em ~96% das linhas do CSV oficial de 2013. Nos anos com os dois campos
# preenchidos (verificado em 2012, 2014 e 2024), a relação categoria → rede é determinística:
# 1 Pública Federal, 2 Pública Estadual, 3 Pública Municipal, 7 Especial → 1 (Pública);
# 4 Privada com fins lucrativos, 5 Privada sem fins lucrativos → 2 (Privada).
# Usada **apenas** para preencher TP_REDE nulo; conflitos são contados no relatório.
CATEGORIA_TO_REDE: dict[str, str] = {"1": "1", "2": "1", "3": "1", "7": "1", "4": "2", "5": "2"}

# Atributos que identificam o curso na base padronizada (TP_DIMENSAO é somado/descartado)
GROUP_KEYS: list[str] = [v for k, v in ATTRIBUTE_COLUMNS.items() if k != "TP_DIMENSAO"]
COUNT_FIELDS: list[str] = list(COUNT_COLUMNS.values())

NIVEL_GRADUACAO = "1"
NIVEL_SEQUENCIAL = "2"
MODALIDADES = {"1": "presencial", "2": "ead"}
REDES = {"1": "publica", "2": "privada"}
DIMENSAO_EAD_SOMENTE_BRASIL = "3"


def canonical(name: str) -> str:
    clean = name.strip().strip('"').strip().upper()
    return COLUMN_ALIASES.get(clean, clean)
