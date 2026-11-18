"""Configurações do projeto (pastas, anos e endereços)."""

import os
from pathlib import Path

# caminhos relativos à raiz do repositório, não à pasta de onde o comando foi chamado
RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
BRUTOS = DADOS / "brutos"
PROCESSADOS = DADOS / "processados"
BASE = DADOS / "evasao.duckdb"
SITE = RAIZ / "web"

ANOS = range(2009, 2025)

URL_INEP = "https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_{ano}.zip"
PAGINA_INEP = (
    "https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/"
    "censo-da-educacao-superior"
)

# origens liberadas no CORS, separadas por vírgula
CORS = [o.strip() for o in os.getenv("EVASAO_CORS", "http://localhost:5173").split(",")
        if o.strip()]


def caminho_zip(ano, pasta=BRUTOS):
    return Path(pasta) / f"microdados_censo_da_educacao_superior_{ano}.zip"
