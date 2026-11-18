"""Reprodução fiel do classificador por palavras-chave do notebook original (Untitled3.ipynb).

Mantido **apenas para auditoria** (comparar com a classificação CINE e quantificar erros).
Não usar em produção. Defeitos conhecidos, reproduzidos de propósito:
- ordem das regras: "física" (Exatas) é testada antes de "educação física" (Saúde), então
  Educação Física vai para Exatas;
- "biologia" não casa com "Ciências Biológicas"; "economia" não casa com "Ciências Econômicas";
- qualquer nome não reconhecido (Agronomia, Arquitetura, Radiologia, Estatística...) vai para
  Humanas por padrão, inclusive valores ausentes.
"""

from __future__ import annotations

EXATAS = "1 - Ciências Exatas e Tecnologia"
SAUDE = "2 - Ciências da Natureza e Saúde"
GESTAO = "3 - Gestão e Negócios"
HUMANAS = "4 - Ciências Humanas, Sociais e Artes"

LEGACY_TO_AREA = {
    EXATAS: "EXATAS_TECNOLOGIA",
    SAUDE: "NATUREZA_SAUDE",
    GESTAO: "GESTAO_NEGOCIOS",
    HUMANAS: "HUMANAS_SOCIAIS_ARTES",
}

_EXATAS_KW = [
    "engenharia",
    "computaç",
    "física",
    "matemática",
    "sistemas",
    "tecnologia",
    "química",
    "informática",
    "análise e des",
    "dados",
    "jogos",
    "redes",
    "telecom",
]
_SAUDE_KW = [
    "medicina",
    "enfermagem",
    "biologia",
    "farmácia",
    "nutrição",
    "odontologia",
    "veterinária",
    "fisioterapia",
    "educação física",
    "saúde",
    "biomedi",
    "terapia ocupacional",
    "fonoaudiologia",
]
_GESTAO_KW = [
    "administra",
    "contábe",
    "economia",
    "gestão",
    "negócios",
    "logística",
    "marketing",
    "finanças",
    "recursos humanos",
    "comércio",
    "processos gerenciais",
]


def classificar_area_legado(nome_curso: object) -> str:
    if not isinstance(nome_curso, str):
        return HUMANAS
    nome = nome_curso.lower()
    if any(x in nome for x in _EXATAS_KW):
        return EXATAS
    if any(x in nome for x in _SAUDE_KW):
        return SAUDE
    if any(x in nome for x in _GESTAO_KW):
        return GESTAO
    return HUMANAS
