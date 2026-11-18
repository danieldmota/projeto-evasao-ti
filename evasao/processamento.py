"""Lê o CSV de cursos de cada ano direto do ZIP e grava um Parquet agregado por curso."""

import hashlib
import json
import logging
import zipfile
from datetime import datetime

import pandas as pd

from evasao.coleta import ler_registro, verificar_zip
from evasao.config import BRUTOS, PROCESSADOS, caminho_zip

log = logging.getLogger(__name__)

COLUNAS = {
    "NU_ANO_CENSO": "ano",
    "CO_CURSO": "co_curso",
    "NO_CURSO": "no_curso",
    "TP_NIVEL_ACADEMICO": "tp_nivel_academico",
    "TP_MODALIDADE_ENSINO": "tp_modalidade_ensino",
    "TP_REDE": "tp_rede",
    "TP_CATEGORIA_ADMINISTRATIVA": "tp_categoria_administrativa",
    "TP_DIMENSAO": "tp_dimensao",
    "CO_CINE_ROTULO": "co_cine_rotulo",
    "NO_CINE_ROTULO": "no_cine_rotulo",
    "CO_CINE_AREA_GERAL": "co_cine_area_geral",
    "NO_CINE_AREA_GERAL": "no_cine_area_geral",
}
CONTAGENS = {
    "QT_CURSO": "qt_cursos",
    "QT_ING": "ingressantes",
    "QT_MAT": "matriculas",
    "QT_CONC": "concluintes",
    "QT_SIT_TRANCADA": "trancadas",
    "QT_SIT_DESVINCULADO": "desvinculados",
    "QT_SIT_TRANSFERIDO": "transferidos",
    "QT_SIT_FALECIDO": "falecidos",
}
# em 2020 o CSV oficial chama a coluna de CO_CINE_ROTULO2 (mesmo conteúdo)
APELIDOS = {"CO_CINE_ROTULO2": "CO_CINE_ROTULO"}

# 2013 vem com TP_REDE vazio em quase todas as linhas. Nos outros anos a categoria
# administrativa define a rede sem exceção: 1, 2, 3 e 7 são públicas; 4 e 5 privadas.
CATEGORIA_REDE = {"1": "1", "2": "1", "3": "1", "7": "1", "4": "2", "5": "2"}

# o curso é a combinação destes atributos; TP_DIMENSAO e a categoria são descartadas
CHAVES = [
    "ano",
    "co_curso",
    "no_curso",
    "tp_nivel_academico",
    "tp_modalidade_ensino",
    "tp_rede",
    "co_cine_rotulo",
    "no_cine_rotulo",
    "co_cine_area_geral",
    "no_cine_area_geral",
]


def nome_coluna(nome):
    nome = nome.strip().strip('"').strip().upper()
    return APELIDOS.get(nome, nome)


def converter_contagens(bloco, ano):
    for col in CONTAGENS.values():
        num = pd.to_numeric(bloco[col], errors="coerce")
        ruins = bloco[col].notna() & num.isna()
        if ruins.any():
            exemplos = bloco.loc[ruins, col].head(3).tolist()
            raise ValueError(f"{ano}: valores não numéricos em {col}: {exemplos}")
        if (num < 0).any() or (num.dropna() % 1 != 0).any():
            raise ValueError(f"{ano}: valores negativos ou não inteiros em {col}")
        bloco[col] = num.astype("Int64")


def ler_cursos(caminho, ano, tamanho_bloco=200_000):
    """Devolve (cursos agregados, info de qualidade) para o ZIP de um ano."""
    membro, md5_ok = verificar_zip(caminho, ano)
    avisos = [] if md5_ok else ["ZIP sem md5 oficial: integridade do CSV não verificada"]

    with zipfile.ZipFile(caminho) as zf:
        with zf.open(membro) as f:
            cabecalho = list(pd.read_csv(f, sep=";", encoding="latin1", nrows=0).columns)
        nomes = {c: nome_coluna(c) for c in cabecalho}
        necessarias = COLUNAS | CONTAGENS
        faltando = [c for c in necessarias if c not in nomes.values()]
        if faltando:
            raise ValueError(f"{ano}: colunas ausentes no CSV: {faltando}")
        usar = [c for c in cabecalho if nomes[c] in necessarias]
        if len(usar) != len(necessarias):
            raise ValueError(f"{ano}: colunas repetidas no CSV: {usar}")
        renomear = {c: necessarias[nomes[c]] for c in usar}

        partes = []
        linhas = derivadas = nulos_estranhos = 0
        with zf.open(membro) as f:
            leitor = pd.read_csv(
                f,
                sep=";",
                encoding="latin1",
                usecols=usar,
                dtype=str,
                keep_default_na=False,
                na_values=[""],
                chunksize=tamanho_bloco,
            )
            for bloco in leitor:
                bloco = bloco.rename(columns=renomear)
                for col in COLUNAS.values():
                    # códigos CINE vêm com aspas extras desde a republicação de 2022
                    bloco[col] = bloco[col].str.strip().str.strip('"').str.strip().replace("", None)
                converter_contagens(bloco, ano)

                if set(bloco["ano"].dropna()) != {str(ano)}:
                    raise ValueError(f"{ano}: NU_ANO_CENSO diferente do ano do arquivo")

                falta = bloco["tp_rede"].isna()
                categoria = bloco.loc[falta, "tp_categoria_administrativa"].map(CATEGORIA_REDE)
                bloco.loc[falta, "tp_rede"] = categoria
                derivadas += int(categoria.notna().sum())

                # EaD com TP_DIMENSAO=3 só tem QT_CURSO; as linhas por município (2) não têm
                # QT_CURSO. Fora disso, nulo é estranho e vira aviso.
                dim = bloco["tp_dimensao"]
                for col in CONTAGENS.values():
                    esperado = dim.isin(["2", "4"]) if col == "qt_cursos" else dim == "3"
                    nulos_estranhos += int((bloco[col].isna() & ~esperado).sum())

                linhas += len(bloco)
                somas = bloco.groupby(CHAVES, dropna=False)[list(CONTAGENS.values())]
                partes.append(somas.sum(min_count=1))

    if not partes:
        raise ValueError(f"{ano}: CSV sem linhas")
    df = pd.concat(partes).groupby(level=CHAVES, dropna=False).sum(min_count=1).reset_index()
    df["ano"] = df["ano"].astype(int)
    for col in CONTAGENS.values():
        df[col] = df[col].astype("Int64")

    if derivadas:
        avisos.append(
            f"TP_REDE vazio em {derivadas} linhas; preenchido pela TP_CATEGORIA_ADMINISTRATIVA"
        )
    if nulos_estranhos:
        avisos.append(f"{nulos_estranhos} contagens nulas fora do padrão de TP_DIMENSAO")
    if df["co_cine_rotulo"].isna().any():
        avisos.append(f"{int(df['co_cine_rotulo'].isna().sum())} cursos sem código CINE")
    if df["tp_rede"].isna().any():
        avisos.append(f"{int(df['tp_rede'].isna().sum())} cursos sem rede identificada")

    info = {
        "ano": ano,
        "arquivo": caminho.name,
        "membro": membro,
        "md5_ok": md5_ok,
        "linhas": linhas,
        "cursos": len(df),
        "avisos": avisos,
    }
    return df, info


def processar_ano(ano, brutos=BRUTOS, saida=PROCESSADOS, forcar=False):
    arquivo = caminho_zip(ano, brutos)
    if not arquivo.exists():
        raise FileNotFoundError(f"{arquivo} não existe (rode: python -m evasao baixar)")
    with arquivo.open("rb") as f:
        sha256 = hashlib.file_digest(f, "sha256").hexdigest()

    saida.mkdir(parents=True, exist_ok=True)
    parquet = saida / f"cursos_{ano}.parquet"
    arq_info = saida / f"cursos_{ano}.json"
    if not forcar and parquet.exists() and arq_info.exists():
        antigo = json.loads(arq_info.read_text(encoding="utf-8"))
        if antigo.get("sha256_zip") == sha256:
            log.info("%s sem mudanças, pulando", ano)
            return antigo

    df, info = ler_cursos(arquivo, ano)
    temp = parquet.with_suffix(".tmp")
    df.to_parquet(temp, index=False)
    temp.replace(parquet)

    info["sha256_zip"] = sha256
    info["fonte_last_modified"] = ler_registro(brutos).get(str(ano), {}).get("last_modified")
    info["processado_em"] = datetime.now().astimezone().isoformat(timespec="seconds")
    arq_info.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("%s: %d linhas, %d cursos, %d avisos", ano, info["linhas"], info["cursos"],
             len(info["avisos"]))
    return info
