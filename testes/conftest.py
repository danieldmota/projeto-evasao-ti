"""Dados SINTÉTICOS para os testes. Todos os números são inventados (não são do INEP)."""

import hashlib
import io
import zipfile

import pytest

from evasao import api
from evasao.consolidacao import consolidar
from evasao.processamento import processar_ano

CABECALHO = [
    "NU_ANO_CENSO", "NO_REGIAO", "SG_UF", "CO_MUNICIPIO", "TP_DIMENSAO",
    "TP_CATEGORIA_ADMINISTRATIVA", "TP_REDE", "CO_IES", "NO_CURSO", "CO_CURSO",
    "NO_CINE_ROTULO", "CO_CINE_ROTULO", "CO_CINE_AREA_GERAL", "NO_CINE_AREA_GERAL",
    "TP_GRAU_ACADEMICO", "TP_MODALIDADE_ENSINO", "TP_NIVEL_ACADEMICO", "QT_CURSO", "QT_VG_TOTAL",
    "QT_ING", "QT_MAT", "QT_CONC", "QT_SIT_TRANCADA", "QT_SIT_DESVINCULADO",
    "QT_SIT_TRANSFERIDO", "QT_SIT_FALECIDO",
]

CINE = {
    "0615S02": ("Sistemas de informação", "06", "Computação e TIC"),
    "0915E01": ("Educação física", "09", "Saúde e bem-estar"),
    "0113P01": ("Pedagogia", "01", "Educação"),
    "0011A09": ("ABI Saúde e bem-estar", "00", "Programas básicos"),
    "0732E01": ("Engenharia civil", "07", "Engenharia, produção e construção"),
    "9999X99": ("Código inexistente (teste)", "99", "Inexistente"),
}


def linha(ano, co_curso, nome, cine, dimensao=1, modalidade=1, nivel=1, rede=2, categoria=4,
          qt_curso=1, ing=0, mat=0, conc=0, tranc=0, desv=0, transf=0, fal=0):
    no_cine, geral, no_geral = CINE[cine]
    return {
        "NU_ANO_CENSO": ano, "NO_REGIAO": "Norte", "SG_UF": "RO", "CO_MUNICIPIO": "1100023",
        "TP_DIMENSAO": dimensao, "TP_CATEGORIA_ADMINISTRATIVA": categoria, "TP_REDE": rede,
        "CO_IES": 999, "NO_CURSO": nome, "CO_CURSO": co_curso, "NO_CINE_ROTULO": no_cine,
        "CO_CINE_ROTULO": f'"""{cine}"""',  # o INEP coloca aspas extras no código
        "CO_CINE_AREA_GERAL": geral, "NO_CINE_AREA_GERAL": no_geral, "TP_GRAU_ACADEMICO": 1,
        "TP_MODALIDADE_ENSINO": modalidade, "TP_NIVEL_ACADEMICO": nivel, "QT_CURSO": qt_curso,
        "QT_VG_TOTAL": 10, "QT_ING": ing, "QT_MAT": mat, "QT_CONC": conc, "QT_SIT_TRANCADA": tranc,
        "QT_SIT_DESVINCULADO": desv, "QT_SIT_TRANSFERIDO": transf, "QT_SIT_FALECIDO": fal,
    }


def linhas_padrao(ano, escala=1):
    s = escala
    return [
        linha(ano, 1, "SISTEMAS DE INFORMAÇÃO", "0615S02", mat=100 * s, tranc=25 * s, desv=10,
              transf=2, conc=10, ing=40),
        # EaD: uma linha por município (sem QT_CURSO) + linha nível Brasil (só QT_CURSO)
        linha(ano, 2, "ANÁLISE E DESENVOLVIMENTO DE SISTEMAS", "0615S02", dimensao=2,
              modalidade=2, qt_curso="", mat=300 * s, tranc=90 * s, desv=60, fal=1),
        linha(ano, 2, "ANÁLISE E DESENVOLVIMENTO DE SISTEMAS", "0615S02", dimensao=2,
              modalidade=2, qt_curso="", mat=200 * s, tranc=10 * s, desv=40),
        linha(ano, 2, "ANÁLISE E DESENVOLVIMENTO DE SISTEMAS", "0615S02", dimensao=3,
              modalidade=2, qt_curso=1, mat="", tranc="", desv="", transf="", fal="", ing="",
              conc=""),
        linha(ano, 3, "EDUCAÇÃO FÍSICA", "0915E01", rede=1, categoria=1, mat=400 * s,
              tranc=20 * s, desv=30, transf=1),
        linha(ano, 4, "PEDAGOGIA", "0113P01", mat=1000 * s, tranc=100 * s, desv=50, transf=5,
              fal=1),
        linha(ano, 5, "ABI - SAÚDE", "0011A09", mat=50, tranc=5, desv=1),
        linha(ano, 6, "ENGENHARIA CIVIL", "0732E01", mat=500 * s, tranc=50 * s, desv=20,
              transf=3),
        linha(ano, 7, "CURSO EXPERIMENTAL", "9999X99", mat=10, tranc=1),
        # sequencial: não entra nas estatísticas de graduação
        linha(ano, 8, "SEQUENCIAL DE TI", "0615S02", nivel=2, mat=999, tranc=999),
    ]


def gerar_csv(linhas, cabecalho=CABECALHO):
    texto = [";".join(cabecalho)]
    texto += [";".join(str(lin.get(c, "")) for c in cabecalho) for lin in linhas]
    return ("\n".join(texto) + "\n").encode("latin1")


def gerar_zip(caminho, ano, conteudo_csv, md5_errado=False):
    raiz = f"Microdados do Censo da Educação Superior {ano}"
    md5 = "0" * 32 if md5_errado else hashlib.md5(conteudo_csv).hexdigest()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{raiz}/dados/MICRODADOS_CADASTRO_CURSOS_{ano}.CSV", conteudo_csv)
        zf.writestr(f"{raiz}/dados/md5_microdados_ed_superior_{ano}.txt",
                    f"{md5} *MICRODADOS_CADASTRO_CURSOS_{ano}.csv\r\n")
    caminho.write_bytes(buf.getvalue())
    return caminho


@pytest.fixture
def criar_zip(tmp_path):
    def criar(ano=2023, linhas=None, cabecalho=CABECALHO, md5_errado=False):
        linhas = linhas_padrao(ano) if linhas is None else linhas
        destino = tmp_path / "brutos" / f"microdados_censo_da_educacao_superior_{ano}.zip"
        destino.parent.mkdir(exist_ok=True)
        return gerar_zip(destino, ano, gerar_csv(linhas, cabecalho), md5_errado)

    return criar


@pytest.fixture
def base_teste(tmp_path, criar_zip, monkeypatch):
    """Base com 2021 e 2023 (fictícios); 2022 e 2024 ficam ausentes de propósito."""
    for ano, escala in ((2021, 1), (2023, 2)):
        criar_zip(ano, linhas_padrao(ano, escala))
        processar_ano(ano, brutos=tmp_path / "brutos", saida=tmp_path / "processados")
    base = consolidar(tmp_path / "processados", tmp_path / "evasao.duckdb", range(2021, 2025))
    monkeypatch.setattr(api, "BASE", base)
    return base
