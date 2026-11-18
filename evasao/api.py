"""API somente leitura (FastAPI) sobre a base dados/evasao.duckdb; também serve o site web/."""

from typing import Literal

import duckdb
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from evasao import config
from evasao.classificacao import (
    AREAS,
    REGRA_TI,
    SEGMENTOS,
    VERSAO_MAPEAMENTO,
    carregar_mapeamento,
)

BASE = config.BASE  # os testes trocam por uma base temporária

FONTE = {
    "nome": "Microdados do Censo da Educação Superior",
    "instituicao": "Instituto Nacional de Estudos e Pesquisas Educacionais Anísio Teixeira (INEP)",
    "url": config.PAGINA_INEP,
    "arquivo": "MICRODADOS_CADASTRO_CURSOS_AAAA.CSV (dentro do ZIP anual)",
    "nota": (
        "Estatísticas calculadas por este projeto a partir dos microdados públicos. "
        "Não são estatísticas oficiais publicadas pelo INEP."
    ),
}
UNIDADE = (
    "Vínculos de aluno a curso de graduação no ano de referência (não pessoas). Taxas são "
    "proporções de 0 a 1."
)
ESCOPO = (
    "Cursos de graduação (TP_NIVEL_ACADEMICO = 1), presenciais e a distância, todas as redes. "
    "Cursos sequenciais de formação específica são excluídos."
)

# somas primeiro, taxa depois (razão de somas, nunca média de percentuais)
INDICADORES_SQL = """
    SUM(matriculas) AS matriculas,
    SUM(trancadas) AS trancadas,
    SUM(desvinculados) AS desvinculados,
    SUM(transferidos) AS transferidos,
    SUM(falecidos) AS falecidos,
    SUM(concluintes) AS concluintes,
    SUM(ingressantes) AS ingressantes,
    SUM(qt_cursos) AS qt_cursos,
    SUM(matriculas) + SUM(trancadas) AS denominador_trancamento,
    SUM(matriculas) + SUM(trancadas) + SUM(desvinculados) + SUM(transferidos)
        + SUM(falecidos) AS vinculos_total,
    SUM(trancadas) / NULLIF(SUM(matriculas) + SUM(trancadas), 0) AS taxa_trancamento,
    SUM(trancadas) / NULLIF(SUM(matriculas) + SUM(trancadas) + SUM(desvinculados)
        + SUM(transferidos) + SUM(falecidos), 0) AS participacao_trancadas_vinculos,
    SUM(desvinculados) / NULLIF(SUM(matriculas) + SUM(trancadas) + SUM(desvinculados)
        + SUM(transferidos) + SUM(falecidos), 0) AS taxa_desvinculacao
"""

# group_by -> (expressão do código, expressão do nome)
GRUPOS = {
    "area": ("area", "area_nome"),
    "segmento": ("segmento", "segmento_nome"),
    "cine_geral": (
        "coalesce(co_cine_area_geral, 'SEM_CINE')",
        "coalesce(no_cine_area_geral, 'Sem código CINE')",
    ),
    "total": ("'TOTAL'", "'Total (todas as áreas)'"),
}

Area = Literal[
    "EXATAS_TECNOLOGIA", "NATUREZA_SAUDE", "GESTAO_NEGOCIOS", "HUMANAS_SOCIAIS_ARTES",
    "NAO_CLASSIFICADO",
]
GroupBy = Literal["area", "segmento", "cine_geral", "total"]

# busca no nome do curso sem acento e sem diferenciar maiúsculas
BUSCA_NOME = "strip_accents(lower(no_cine_rotulo)) LIKE '%' || strip_accents(lower(?)) || '%'"

app = FastAPI(
    title="API Evasão em TI — Censo da Educação Superior",
    description="Matrículas e trancamentos em cursos de graduação (INEP, 2009–2024). "
    "Metodologia em /api/v1/methodology.",
)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS, allow_methods=["GET"],
                   allow_headers=["*"])


def erro(status, codigo, mensagem):
    corpo = {"error": {"code": codigo, "message": mensagem}}
    return JSONResponse(status_code=status, content=corpo)


@app.exception_handler(StarletteHTTPException)
def tratar_http(_request, exc):
    codigos = {404: "nao_encontrado", 422: "parametro_invalido", 503: "dados_indisponiveis"}
    return erro(exc.status_code, codigos.get(exc.status_code, "erro"), str(exc.detail))


@app.exception_handler(RequestValidationError)
def tratar_validacao(_request, exc):
    partes = [f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors()]
    return erro(422, "parametro_invalido", "Parâmetros inválidos: " + "; ".join(partes))


# acesso à base


def conectar():
    if not BASE.exists():
        raise HTTPException(503, "Base de dados não encontrada; rode: python -m evasao consolidar")
    return duckdb.connect(str(BASE), read_only=True)


def consultar(con, sql, params=()):
    cur = con.execute(sql, list(params))
    colunas = [d[0] for d in cur.description]
    return [dict(zip(colunas, linha, strict=True)) for linha in cur.fetchall()]


def filtros(
    year_start: int | None = Query(None, ge=1995, le=2100),
    year_end: int | None = Query(None, ge=1995, le=2100),
    area: list[Area] | None = Query(None),
    ti: bool | None = Query(None),
    modalidade: Literal["presencial", "ead"] | None = Query(None),
    rede: Literal["publica", "privada"] | None = Query(None),
):
    if year_start is not None and year_end is not None and year_start > year_end:
        raise HTTPException(422, "year_start deve ser menor ou igual a year_end")
    return {"year_start": year_start, "year_end": year_end, "area": area, "ti": ti,
            "modalidade": modalidade, "rede": rede}


def where(f):
    """Monta o WHERE com parâmetros (?) a partir dos filtros."""
    condicoes, params = ["TRUE"], []
    if f["year_start"] is not None:
        condicoes.append("ano >= ?")
        params.append(f["year_start"])
    if f["year_end"] is not None:
        condicoes.append("ano <= ?")
        params.append(f["year_end"])
    if f["area"]:
        condicoes.append(f"area IN ({', '.join('?' * len(f['area']))})")
        params += f["area"]
    if f["ti"] is not None:
        condicoes.append("is_ti = ?")
        params.append(f["ti"])
    for campo in ("modalidade", "rede"):
        if f[campo]:
            condicoes.append(f"{campo} = ?")
            params.append(f[campo])
    return " AND ".join(condicoes), params


def pct(valor):
    return f"{valor:.2%}".replace(".", ",")


def montar_meta(con, f=None, extras=None, avisos=None):
    f = f or {}
    anos = consultar(con, "SELECT ano, status, comparabilidade FROM anos ORDER BY ano")
    disponiveis = [a["ano"] for a in anos if a["status"] == "disponivel"]
    todos = [a["ano"] for a in anos]
    inicio = f.get("year_start") or min(todos + [f.get("year_end") or 9999])
    fim = f.get("year_end") or max(todos + [inicio])
    com_dados = [a for a in disponiveis if inicio <= a <= fim]
    ausentes = [a for a in range(inicio, fim + 1) if a not in disponiveis]

    avisos = list(avisos or [])
    if f:
        sql, params = where(f)
        total, nc, baixa = con.execute(f"""
            SELECT SUM(matriculas),
                   SUM(matriculas) FILTER (WHERE area = 'NAO_CLASSIFICADO'),
                   SUM(matriculas) FILTER (WHERE confianca = 'baixa')
            FROM fato WHERE {sql}""", params).fetchone()
        if total and nc:
            avisos.append(f"{pct(nc / total)} das matrículas do recorte estão em cursos "
                          "'Não classificado' (ex.: Área Básica de Ingresso).")
        if total and baixa:
            avisos.append(f"{pct(baixa / total)} das matrículas do recorte estão em rótulos com "
                          "correspondência de confiança 'baixa'.")
    if ausentes:
        avisos.append(f"Sem dados para {ausentes}: anos ausentes não são tratados como zero.")
    atencao = [a["ano"] for a in anos
               if a["comparabilidade"] == "atencao" and a["ano"] in com_dados]
    if atencao:
        avisos.append(f"Anos com alerta de comparabilidade no período: {atencao} "
                      "(detalhes em /api/v1/years).")

    filtros_usados = {k: v for k, v in {**f, **(extras or {})}.items() if v is not None}
    return {
        "fonte": FONTE,
        "unidade": UNIDADE,
        "escopo": ESCOPO,
        "periodo": {
            "solicitado_inicio": inicio,
            "solicitado_fim": fim,
            "anos_com_dados": com_dados,
            "anos_ausentes": ausentes,
        },
        "classificacao": {"versao_mapeamento": VERSAO_MAPEAMENTO, "regra_ti": REGRA_TI},
        "filtros": filtros_usados,
        "avisos": avisos,
    }


# rotas


@app.get("/api/v1/health")
def saude():
    if not BASE.exists():
        return {"status": "sem_dados", "anos_disponiveis": []}
    with conectar() as con:
        anos = con.execute("SELECT ano FROM anos WHERE status = 'disponivel' ORDER BY ano")
        return {"status": "ok", "anos_disponiveis": [a for (a,) in anos.fetchall()]}


@app.get("/api/v1/years")
def anos():
    with conectar() as con:
        dados = consultar(con, "SELECT * FROM anos ORDER BY ano")
        return {"data": dados, "meta": montar_meta(con)}


@app.get("/api/v1/statistics/annual")
def estatisticas_anuais(f: dict = Depends(filtros), group_by: GroupBy = "area"):
    codigo, nome = GRUPOS[group_by]
    sql, params = where(f)
    with conectar() as con:
        dados = consultar(con, f"""
            SELECT ano, {codigo} AS grupo_codigo, {nome} AS grupo_nome, {INDICADORES_SQL}
            FROM fato WHERE {sql}
            GROUP BY ALL ORDER BY ano, grupo_codigo""", params)
        return {"data": dados, "meta": montar_meta(con, f, {"group_by": group_by})}


@app.get("/api/v1/statistics/summary")
def estatisticas_resumo(f: dict = Depends(filtros), group_by: GroupBy = "area"):
    codigo, nome = GRUPOS[group_by]
    sql, params = where(f)
    aviso = ("Consolidado = soma de vínculos-ano de todos os anos com dados no período. "
             "Não representa número de pessoas distintas.")
    with conectar() as con:
        dados = consultar(con, f"""
            SELECT {codigo} AS grupo_codigo, {nome} AS grupo_nome, {INDICADORES_SQL}
            FROM fato WHERE {sql}
            GROUP BY ALL ORDER BY grupo_codigo""", params)
        return {"data": dados, "meta": montar_meta(con, f, {"group_by": group_by}, [aviso])}


@app.get("/api/v1/statistics/courses")
def estatisticas_cursos(
    f: dict = Depends(filtros),
    q: str | None = Query(None, min_length=2, max_length=80),
    sort_by: Literal["matriculas", "trancadas", "taxa_trancamento",
                     "no_cine_rotulo"] = "matriculas",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_denominador: int = Query(0, ge=0),
):
    sql, params = where(f)
    if q:
        sql += " AND " + BUSCA_NOME
        params.append(q)
    # agrupa pelo NOME do curso: a revisão CINE de 2024 trocou códigos mas manteve os nomes
    agrupado = f"""
        SELECT no_cine_rotulo, area, area_nome, segmento, is_ti,
               list_sort(list_distinct(list(co_cine_rotulo))) AS codigos_cine,
               list_sort(list_distinct(list(ano))) AS anos_com_dados,
               {INDICADORES_SQL}
        FROM fato WHERE {sql}
        GROUP BY ALL
        HAVING coalesce(SUM(matriculas) + SUM(trancadas), 0) >= ?"""
    params.append(min_denominador)
    with conectar() as con:
        total = con.execute(f"SELECT count(*) FROM ({agrupado})", params).fetchone()[0]
        dados = consultar(con, f"""
            SELECT * FROM ({agrupado})
            ORDER BY {sort_by} {order} NULLS LAST, no_cine_rotulo
            LIMIT ? OFFSET ?""", [*params, limit, offset])
        extras = {"q": q, "sort_by": sort_by, "order": order,
                  "min_denominador": min_denominador or None}
        meta = montar_meta(con, f, extras, [
            "Agregação por rótulo CINE (nome padronizado do curso), somando todas as IES."
        ])
        meta["paginacao"] = {"total": total, "limit": limit, "offset": offset}
        return {"data": dados, "meta": meta}


@app.get("/api/v1/areas")
def areas():
    with conectar() as con:
        por_area = dict(con.execute("SELECT area, count(*) FROM rotulos GROUP BY area").fetchall())
        por_seg = dict(con.execute(
            "SELECT segmento, count(*) FROM rotulos GROUP BY segmento").fetchall())
        dados = [
            {"codigo": c, "nome": n, "tipo": "area", "rotulos_cine": por_area.get(c, 0)}
            for c, n in AREAS.items()
        ] + [
            {"codigo": c, "nome": n, "tipo": "segmento", "rotulos_cine": por_seg.get(c, 0)}
            for c, n in SEGMENTOS.items()
        ]
        regras = list(carregar_mapeamento().values())
        return {"data": dados, "regras": regras, "meta": montar_meta(con)}


@app.get("/api/v1/classification/rotulos")
def rotulos(
    area: list[Area] | None = Query(None),
    ti: bool | None = Query(None),
    q: str | None = Query(None, min_length=2, max_length=80),
):
    condicoes, params = ["TRUE"], []
    if area:
        condicoes.append(f"area IN ({', '.join('?' * len(area))})")
        params += area
    if ti is not None:
        condicoes.append("is_ti = ?")
        params.append(ti)
    if q:
        condicoes.append(BUSCA_NOME)
        params.append(q)
    with conectar() as con:
        dados = consultar(con, f"SELECT * FROM rotulos WHERE {' AND '.join(condicoes)} "
                               "ORDER BY co_cine_rotulo", params)
        return {"data": dados, "meta": montar_meta(con, extras={"area": area, "ti": ti, "q": q})}


@app.get("/api/v1/methodology")
def metodologia():
    return METODOLOGIA


METODOLOGIA = {
    "fonte": FONTE,
    "unidade": UNIDADE,
    "escopo": ESCOPO,
    "variaveis": {
        "matriculas": {
            "coluna_inep": "QT_MAT",
            "definicao_oficial": "Soma do número de alunos com situação de vínculo ao curso "
            "igual a Cursando e/ou Formado (Dicionário de Dados INEP).",
        },
        "trancadas": {
            "coluna_inep": "QT_SIT_TRANCADA",
            "definicao_oficial": "Quantidade de alunos com situação de vínculo no curso - "
            "matrícula trancada.",
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
        "concluintes": {"coluna_inep": "QT_CONC",
                        "definicao_oficial": "Quantidade de concluintes."},
        "ingressantes": {
            "coluna_inep": "QT_ING",
            "definicao_oficial": "Cálculo de ingressantes: soma do número de alunos com data de "
            "ingresso de 01 de janeiro e 01 de julho do ano de referência do censo (texto literal "
            "do Dicionário de Dados INEP).",
        },
        "qt_cursos": {"coluna_inep": "QT_CURSO", "definicao_oficial": "Número de cursos."},
    },
    "conceitos": {
        "trancamento": "Situação de vínculo declarada pela IES: o aluno mantém o vínculo, mas "
        "suspendeu temporariamente os estudos. É medido diretamente (QT_SIT_TRANCADA).",
        "matricula": "No Censo, 'matrícula' = vínculos Cursando ou Formado no ano (QT_MAT). Não "
        "inclui trancados, desvinculados, transferidos nem falecidos.",
        "desvinculacao": "Situação de vínculo 'desvinculado do curso' (QT_SIT_DESVINCULADO). É o "
        "mais próximo de saída do curso disponível neste arquivo, mas não distingue abandono, "
        "desistência formal, jubilamento etc.",
        "evasao_desistencia": "Evasão/desistência exige acompanhar o mesmo aluno ao longo dos "
        "anos (coorte). O INEP publica isso nos 'Indicadores de Fluxo da Educação Superior' "
        "(taxa de desistência acumulada). Os microdados agregados por curso não permitem esse "
        "cálculo; este projeto NÃO calcula taxa de evasão.",
        "abandono": "Não há variável de abandono no arquivo de cursos.",
    },
    "indicadores": {
        "taxa_trancamento": {
            "formula": "trancadas / (matriculas + trancadas)",
            "descricao": "Proporção de vínculos com matrícula trancada entre os vínculos "
            "cursando, formados ou trancados no ano de referência.",
            "unidade": "proporção (0–1); multiplique por 100 para percentual",
        },
        "participacao_trancadas_vinculos": {
            "formula": "trancadas / (matriculas + trancadas + desvinculados + transferidos "
            "+ falecidos)",
            "descricao": "Participação das matrículas trancadas no total de vínculos declarados.",
            "unidade": "proporção (0–1)",
        },
        "taxa_desvinculacao": {
            "formula": "desvinculados / (matriculas + trancadas + desvinculados + transferidos "
            "+ falecidos)",
            "descricao": "Participação de alunos desvinculados do curso no total de vínculos. "
            "Indicador complementar; não equivale à taxa oficial de evasão/desistência do INEP.",
            "unidade": "proporção (0–1)",
        },
    },
    "agregacao": "Todas as agregações (por área, período ou curso) somam numeradores e "
    "denominadores e só então calculam a taxa (razão de somas). Nunca é feita média simples de "
    "percentuais.",
    "classificacao": {
        "versao_mapeamento": VERSAO_MAPEAMENTO,
        "ordem_resolucao": ["rotulo", "detalhada", "especifica", "geral"],
        "regra_ti": REGRA_TI,
        "sem_regra": "Cursos sem código CINE válido ou sem regra → 'Não classificado' "
        "(nunca uma área padrão).",
    },
    "limitacoes": [
        "Contagens são de vínculos-ano, não de pessoas: o mesmo estudante aparece em todos os "
        "anos em que estiver vinculado. Somas de vários anos ('consolidado do período') medem "
        "vínculos-ano, não 'pessoas que trancaram'.",
        "QT_MAT inclui formados no ano; a taxa de trancamento usa um denominador que mistura "
        "alunos cursando, formados e trancados.",
        "As 4 áreas do projeto são uma correspondência própria sobre a CINE (versionada), não uma "
        "classificação oficial. Rótulos com confiança 'baixa' e 'Não classificado' são informados.",
        "A CINE classifica licenciaturas (inclusive Matemática, Física e Computação) em Educação, "
        "portanto elas entram em Humanas e não em Exatas/TI.",
        "Anos ausentes não são preenchidos com zero; aparecem em 'anos_ausentes'.",
        "A série 2009–2020 foi republicada pelo INEP em 04/11/2022 no layout atual, com CINE "
        "atribuída retroativamente; o primeiro e o último ano de cada código CINE aparecem em "
        "/api/v1/classification/rotulos.",
        "A seção 'TI' segue a CINE área geral 06; cursos tecnológicos com nome de TI mas outro "
        "código CINE (ex.: engenharia de computação na DCN de Engenharia) não entram em TI.",
    ],
    "aviso_orientacao_vocacional": "O teste vocacional da plataforma é uma ferramenta de "
    "orientação e não constitui diagnóstico psicológico validado.",
}

# o site estático é montado por último para não esconder as rotas /api/v1
if config.SITE.is_dir():
    app.mount("/", StaticFiles(directory=config.SITE, html=True), name="site")
