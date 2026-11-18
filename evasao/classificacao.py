"""Classificação dos cursos nas 4 áreas do projeto a partir do código CINE."""

import csv
import re
from functools import cache
from pathlib import Path

VERSAO_MAPEAMENTO = "1.1.0"  # mudar sempre que mapeamento_cine.csv for alterado
ARQUIVO_MAPEAMENTO = Path(__file__).parent / "mapeamento_cine.csv"

AREAS = {
    "EXATAS_TECNOLOGIA": "Ciências Exatas e Tecnologia",
    "NATUREZA_SAUDE": "Ciências da Natureza e Saúde",
    "GESTAO_NEGOCIOS": "Gestão e Negócios",
    "HUMANAS_SOCIAIS_ARTES": "Ciências Humanas, Sociais e Artes",
    "NAO_CLASSIFICADO": "Não classificado",
}
# mesmas áreas, mas com TI separada do resto de Exatas
SEGMENTOS = {
    "TI": "Tecnologia da Informação (CINE 06)",
    "EXATAS_EXCETO_TI": "Ciências Exatas e Tecnologia (exceto TI)",
    "NATUREZA_SAUDE": AREAS["NATUREZA_SAUDE"],
    "GESTAO_NEGOCIOS": AREAS["GESTAO_NEGOCIOS"],
    "HUMANAS_SOCIAIS_ARTES": AREAS["HUMANAS_SOCIAIS_ARTES"],
    "NAO_CLASSIFICADO": AREAS["NAO_CLASSIFICADO"],
}
REGRA_TI = "CINE área geral 06 — Computação e Tecnologias da Informação e Comunicação (TIC)"

# nível da regra -> quantos caracteres do código CINE (do mais específico ao mais geral)
NIVEIS = {"rotulo": 7, "detalhada": 4, "especifica": 3, "geral": 2}
FORMATO = {
    "rotulo": r"\d{4}[A-Z]\d{2}",
    "detalhada": r"\d{4}",
    "especifica": r"\d{3}",
    "geral": r"\d{2}",
}


@cache
def carregar_mapeamento(arquivo=ARQUIVO_MAPEAMENTO):
    regras = {}
    with open(arquivo, encoding="utf-8", newline="") as f:
        for n, linha in enumerate(csv.DictReader(f), start=2):
            nivel, codigo = linha["nivel"], linha["codigo"]
            if nivel not in NIVEIS or not re.fullmatch(FORMATO[nivel], codigo):
                raise ValueError(f"mapeamento linha {n}: nível/código inválido {nivel} {codigo}")
            if linha["area"] not in AREAS:
                raise ValueError(f"mapeamento linha {n}: área inválida {linha['area']}")
            if linha["confianca"] not in ("alta", "media", "baixa"):
                raise ValueError(f"mapeamento linha {n}: confiança inválida")
            if (nivel, codigo) in regras:
                raise ValueError(f"mapeamento linha {n}: regra repetida {nivel} {codigo}")
            regras[(nivel, codigo)] = linha
    return regras


def sem_classificacao(motivo, is_ti=False):
    return {
        "area": "NAO_CLASSIFICADO",
        "segmento": "NAO_CLASSIFICADO",
        "is_ti": is_ti,
        "regra_nivel": None,
        "regra_codigo": None,
        "confianca": "nenhuma",
        "justificativa": motivo,
    }


def classificar(rotulo):
    """Usa a regra mais específica que existir (rótulo > detalhada > específica > geral).

    Sem código ou sem regra o curso fica NAO_CLASSIFICADO (nunca cai numa área padrão).
    """
    rotulo = str(rotulo or "").strip().strip('"')
    if rotulo in ("", "nan", "<NA>", "None"):
        return sem_classificacao("Curso sem código CINE")
    if not re.fullmatch(FORMATO["rotulo"], rotulo):
        return sem_classificacao(f"Código CINE inválido: {rotulo}")

    is_ti = rotulo[:2] == "06"
    regras = carregar_mapeamento()
    for nivel, tamanho in NIVEIS.items():
        regra = regras.get((nivel, rotulo[:tamanho]))
        if regra:
            area = regra["area"]
            if is_ti:
                segmento = "TI"
            elif area == "EXATAS_TECNOLOGIA":
                segmento = "EXATAS_EXCETO_TI"
            else:
                segmento = area
            return {
                "area": area,
                "segmento": segmento,
                "is_ti": is_ti,
                "regra_nivel": nivel,
                "regra_codigo": rotulo[:tamanho],
                "confianca": regra["confianca"],
                "justificativa": regra["justificativa"],
            }
    return sem_classificacao(f"Nenhuma regra para o CINE {rotulo}", is_ti)


# --- classificador antigo do notebook (Untitled3.ipynb), usado só na auditoria ---
# Os defeitos são de propósito: "física" é testada antes de "educação física" (vai para
# Exatas), "Ciências Biológicas" não casa com "biologia" e tudo que sobra vira Humanas.
PALAVRAS_NOTEBOOK = [
    ("EXATAS_TECNOLOGIA", ["engenharia", "computaç", "física", "matemática", "sistemas",
                           "tecnologia", "química", "informática", "análise e des", "dados",
                           "jogos", "redes", "telecom"]),
    ("NATUREZA_SAUDE", ["medicina", "enfermagem", "biologia", "farmácia", "nutrição",
                        "odontologia", "veterinária", "fisioterapia", "educação física", "saúde",
                        "biomedi", "terapia ocupacional", "fonoaudiologia"]),
    ("GESTAO_NEGOCIOS", ["administra", "contábe", "economia", "gestão", "negócios", "logística",
                         "marketing", "finanças", "recursos humanos", "comércio",
                         "processos gerenciais"]),
]


def classificar_como_notebook(nome_curso):
    if not isinstance(nome_curso, str):
        return "HUMANAS_SOCIAIS_ARTES"
    nome = nome_curso.lower()
    for area, palavras in PALAVRAS_NOTEBOOK:
        if any(p in nome for p in palavras):
            return area
    return "HUMANAS_SOCIAIS_ARTES"
