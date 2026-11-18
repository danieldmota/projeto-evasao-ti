"""Gerador de fixtures SINTÉTICAS no formato do MICRODADOS_CADASTRO_CURSOS_AAAA.CSV.

ATENÇÃO: todos os números aqui são FICTÍCIOS, criados apenas para testar o código.
Não representam estatísticas do INEP.

Reproduz as peculiaridades observadas nos arquivos reais:
- Latin-1, separador ';', cabeçalho com colunas extras além das usadas;
- CO_CINE_ROTULO com aspas triplas no CSV bruto (3 aspas + 0721E01 + 3 aspas);
- cursos EaD repetidos por município (TP_DIMENSAO=2, QT_CURSO vazio) + linha nível Brasil
  (TP_DIMENSAO=3, só QT_CURSO preenchido);
- ZIP com pasta raiz arbitrária e arquivo md5_*.txt.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

HEADER = [
    "NU_ANO_CENSO",
    "NO_REGIAO",
    "CO_REGIAO",
    "NO_UF",
    "SG_UF",
    "CO_UF",
    "NO_MUNICIPIO",
    "CO_MUNICIPIO",
    "IN_CAPITAL",
    "TP_DIMENSAO",
    "TP_ORGANIZACAO_ACADEMICA",
    "TP_CATEGORIA_ADMINISTRATIVA",
    "TP_REDE",
    "CO_IES",
    "NO_CURSO",
    "CO_CURSO",
    "NO_CINE_ROTULO",
    "CO_CINE_ROTULO",
    "CO_CINE_AREA_GERAL",
    "NO_CINE_AREA_GERAL",
    "CO_CINE_AREA_ESPECIFICA",
    "NO_CINE_AREA_ESPECIFICA",
    "CO_CINE_AREA_DETALHADA",
    "NO_CINE_AREA_DETALHADA",
    "TP_GRAU_ACADEMICO",
    "IN_GRATUITO",
    "TP_MODALIDADE_ENSINO",
    "TP_NIVEL_ACADEMICO",
    "QT_CURSO",
    "QT_VG_TOTAL",
    "QT_ING",
    "QT_MAT",
    "QT_MAT_FEM",
    "QT_CONC",
    "QT_SIT_TRANCADA",
    "QT_SIT_DESVINCULADO",
    "QT_SIT_TRANSFERIDO",
    "QT_SIT_FALECIDO",
]

CINE = {
    "0615S02": (
        "Sistemas de informação",
        "06",
        "Computação e Tecnologias da Informação e Comunicação (TIC)",
        "061",
        "Computação e TIC",
        "0615",
        "Gestão e desenvolvimento de sistemas de informação",
    ),
    "0915E01": (
        "Educação física",
        "09",
        "Saúde e bem-estar",
        "091",
        "Saúde",
        "0915",
        "Promoção, prevenção, terapia e reabilitação",
    ),
    "0113P01": (
        "Pedagogia",
        "01",
        "Educação",
        "011",
        "Educação",
        "0113",
        "Formação de professores sem áreas específicas",
    ),
    "0011A09": (
        "ABI Saúde e bem-estar",
        "00",
        "Programas básicos",
        "001",
        "Programas básicos",
        "0011",
        "Programas básicos",
    ),
    "0732E01": (
        "Engenharia civil",
        "07",
        "Engenharia, produção e construção",
        "073",
        "Arquitetura e construção",
        "0732",
        "Engenharia civil e construção",
    ),
    "9999X99": (
        "Código inexistente (teste)",
        "99",
        "Inexistente",
        "999",
        "Inexistente",
        "9999",
        "Inexistente",
    ),
}


def row(
    year: int,
    co_curso: int,
    no_curso: str,
    cine: str,
    *,
    dimensao: int = 1,
    modalidade: int = 1,
    nivel: int = 1,
    rede: int | str = 2,
    categoria: int | str = 4,
    qt_curso: int | str = 1,
    ing: int | str = 0,
    mat: int | str = 0,
    conc: int | str = 0,
    tranc: int | str = 0,
    desv: int | str = 0,
    transf: int | str = 0,
    fal: int | str = 0,
    municipio: str = "1100023",
) -> dict[str, object]:
    name, g, gn, e, en, d, dn = CINE[cine]
    return {
        "NU_ANO_CENSO": year,
        "NO_REGIAO": "Norte",
        "CO_REGIAO": 1,
        "NO_UF": "Rondônia",
        "SG_UF": "RO",
        "CO_UF": 11,
        "NO_MUNICIPIO": "Ariquemes",
        "CO_MUNICIPIO": municipio,
        "IN_CAPITAL": 0,
        "TP_DIMENSAO": dimensao,
        "TP_ORGANIZACAO_ACADEMICA": 1,
        "TP_CATEGORIA_ADMINISTRATIVA": categoria,
        "TP_REDE": rede,
        "CO_IES": 999,
        "NO_CURSO": no_curso,
        "CO_CURSO": co_curso,
        "NO_CINE_ROTULO": name,
        "CO_CINE_ROTULO": f'"""{cine}"""',
        "CO_CINE_AREA_GERAL": g,
        "NO_CINE_AREA_GERAL": gn,
        "CO_CINE_AREA_ESPECIFICA": e,
        "NO_CINE_AREA_ESPECIFICA": en,
        "CO_CINE_AREA_DETALHADA": d,
        "NO_CINE_AREA_DETALHADA": dn,
        "TP_GRAU_ACADEMICO": 1,
        "IN_GRATUITO": 0,
        "TP_MODALIDADE_ENSINO": modalidade,
        "TP_NIVEL_ACADEMICO": nivel,
        "QT_CURSO": qt_curso,
        "QT_VG_TOTAL": 10,
        "QT_ING": ing,
        "QT_MAT": mat,
        "QT_MAT_FEM": 0,
        "QT_CONC": conc,
        "QT_SIT_TRANCADA": tranc,
        "QT_SIT_DESVINCULADO": desv,
        "QT_SIT_TRANSFERIDO": transf,
        "QT_SIT_FALECIDO": fal,
    }


def default_rows(year: int, scale: int = 1) -> list[dict[str, object]]:
    """Conjunto FICTÍCIO cobrindo os casos relevantes."""
    s = scale
    return [
        # TI presencial
        row(
            year,
            1,
            "SISTEMAS DE INFORMAÇÃO",
            "0615S02",
            mat=100 * s,
            tranc=25 * s,
            desv=10 * s,
            transf=2,
            fal=0,
            conc=10,
            ing=40,
        ),
        # TI EaD: duas linhas por município + linha nível Brasil (só QT_CURSO)
        row(
            year,
            2,
            "ANÁLISE E DESENVOLVIMENTO DE SISTEMAS",
            "0615S02",
            dimensao=2,
            modalidade=2,
            qt_curso="",
            mat=300 * s,
            tranc=90 * s,
            desv=60,
            transf=0,
            fal=1,
            municipio="1100023",
        ),
        row(
            year,
            2,
            "ANÁLISE E DESENVOLVIMENTO DE SISTEMAS",
            "0615S02",
            dimensao=2,
            modalidade=2,
            qt_curso="",
            mat=200 * s,
            tranc=10 * s,
            desv=40,
            transf=0,
            fal=0,
            municipio="1100205",
        ),
        row(
            year,
            2,
            "ANÁLISE E DESENVOLVIMENTO DE SISTEMAS",
            "0615S02",
            dimensao=3,
            modalidade=2,
            qt_curso=1,
            mat="",
            tranc="",
            desv="",
            transf="",
            fal="",
            ing="",
            conc="",
            municipio="",
        ),
        # Educação física (bacharelado): Saúde na CINE; o notebook mandava para Exatas
        row(
            year,
            3,
            "EDUCAÇÃO FÍSICA",
            "0915E01",
            rede=1,
            categoria=1,
            mat=400 * s,
            tranc=20 * s,
            desv=30,
            transf=1,
            fal=0,
        ),
        # Pedagogia
        row(year, 4, "PEDAGOGIA", "0113P01", mat=1000 * s, tranc=100 * s, desv=50, transf=5, fal=1),
        # Área Básica de Ingresso: não classificável
        row(year, 5, "ABI - SAÚDE", "0011A09", mat=50, tranc=5, desv=1, transf=0, fal=0),
        # Engenharia civil (Exatas, não TI)
        row(
            year,
            6,
            "ENGENHARIA CIVIL",
            "0732E01",
            mat=500 * s,
            tranc=50 * s,
            desv=20,
            transf=3,
            fal=0,
        ),
        # Código CINE sem regra
        row(year, 7, "CURSO EXPERIMENTAL", "9999X99", mat=10, tranc=1, desv=0, transf=0, fal=0),
        # Sequencial: excluído das estatísticas de graduação
        row(
            year,
            8,
            "SEQUENCIAL DE TI",
            "0615S02",
            nivel=2,
            mat=999,
            tranc=999,
            desv=0,
            transf=0,
            fal=0,
        ),
    ]


def to_csv_bytes(
    rows: list[dict[str, object]], header: list[str] | None = None, encoding: str = "latin1"
) -> bytes:
    header = header or HEADER
    lines = [";".join(header)]
    for r in rows:
        lines.append(";".join("" if r.get(c, "") is None else str(r.get(c, "")) for c in header))
    return ("\n".join(lines) + "\n").encode(encoding)


def write_zip(
    path: Path,
    year: int,
    csv_bytes: bytes,
    *,
    with_md5: bool = True,
    wrong_md5: bool = False,
    root: str | None = None,
) -> Path:
    root = root or f"Microdados do Censo da Educação Superior {year}"
    name = f"MICRODADOS_CADASTRO_CURSOS_{year}.CSV"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{root}/dados/{name}", csv_bytes)
        zf.writestr(f"{root}/leia-me/Leia_me.pdf", b"%PDF-fake")
        if with_md5:
            md5 = hashlib.md5(csv_bytes, usedforsecurity=False).hexdigest()
            if wrong_md5:
                md5 = "0" * 32
            zf.writestr(
                f"{root}/dados/md5_microdados_ed_superior_{year}.txt",
                f"{md5} *MICRODADOS_CADASTRO_CURSOS_{year}.csv\r\n",
            )
    path.write_bytes(buf.getvalue())
    return path
