"""Monta a base DuckDB usada pela API a partir dos Parquets anuais (tudo em SQL)."""

import json
import logging
from datetime import datetime

import duckdb

from evasao.classificacao import (
    AREAS,
    SEGMENTOS,
    VERSAO_MAPEAMENTO,
    classificar,
    classificar_como_notebook,
)
from evasao.config import ANOS, BASE, DADOS, PROCESSADOS

log = logging.getLogger(__name__)

LIMITE_VARIACAO = 0.40  # variação anual acima disso gera alerta

# observações feitas olhando os arquivos oficiais de cada ano
NOTAS_CURADAS = {
    2009: [
        "QT_SIT_TRANSFERIDO é zero em todos os cursos de 2009 (provável ausência de coleta); "
        "indicadores sobre o total de vínculos ficam subestimados no denominador.",
        "Trancadas (+49%) e desvinculados (+112%) saltam de 2009 para 2010; trate comparações "
        "com 2009 com cautela.",
    ],
    2013: [
        "TP_REDE vem vazio na maioria das linhas do CSV oficial; a rede foi derivada de "
        "TP_CATEGORIA_ADMINISTRATIVA (regra determinística verificada em 2012, 2014 e 2024).",
    ],
    2020: [
        "No CSV oficial a coluna se chama CO_CINE_ROTULO2 (tratada como CO_CINE_ROTULO). "
        "Ano marcado pela pandemia de COVID-19: o aumento de trancamentos é plausível como "
        "fenômeno real, não como erro de dados.",
    ],
    2024: [
        "Revisão da CINE Brasil: códigos da área 06 (TI) foram reorganizados (ex.: Sistemas de "
        "informação 0615S02 → 0613S01; Ciência da computação 0614C01 → 0613C01). Os nomes dos "
        "cursos se mantêm, e /statistics/courses agrega por nome para preservar a série.",
        "Quebra na série de TI: 'Engenharia de computação (DCN Computação)' (0616E01, 17.426 "
        "matrículas em 2023) e 'Sistemas embarcados' saíram da área 06 e foram para Engenharia "
        "(0714E04 / 0714S03). Em 2023 isso equivalia a ~2,4% das matrículas de TI.",
    ],
}

SQL_FATO = """
CREATE TABLE fato AS
SELECT
    k.ano,
    k.co_cine_rotulo,
    k.no_cine_rotulo,
    k.co_cine_area_geral,
    k.no_cine_area_geral,
    c.area,
    c.area_nome,
    c.segmento,
    c.segmento_nome,
    c.is_ti,
    c.confianca,
    CASE k.tp_modalidade_ensino WHEN '1' THEN 'presencial' WHEN '2' THEN 'ead'
         ELSE 'nao_informado' END AS modalidade,
    CASE k.tp_rede WHEN '1' THEN 'publica' WHEN '2' THEN 'privada'
         ELSE 'nao_informado' END AS rede,
    SUM(k.qt_cursos)::BIGINT AS qt_cursos,
    SUM(k.ingressantes)::BIGINT AS ingressantes,
    SUM(k.matriculas)::BIGINT AS matriculas,
    SUM(k.concluintes)::BIGINT AS concluintes,
    SUM(k.trancadas)::BIGINT AS trancadas,
    SUM(k.desvinculados)::BIGINT AS desvinculados,
    SUM(k.transferidos)::BIGINT AS transferidos,
    SUM(k.falecidos)::BIGINT AS falecidos
FROM cursos k
JOIN classes c ON c.co_cine_rotulo IS NOT DISTINCT FROM k.co_cine_rotulo
WHERE k.tp_nivel_academico = '1'  -- só graduação (sequenciais ficam de fora)
GROUP BY ALL
ORDER BY ALL
"""

SQL_ROTULOS = """
CREATE TABLE rotulos AS
SELECT
    k.co_cine_rotulo,
    arg_max(k.no_cine_rotulo, k.ano) AS no_cine_rotulo,
    arg_max(k.co_cine_area_geral, k.ano) AS co_cine_area_geral,
    arg_max(k.no_cine_area_geral, k.ano) AS no_cine_area_geral,
    c.area, c.segmento, c.is_ti, c.regra_nivel, c.regra_codigo, c.confianca, c.justificativa,
    min(k.ano) AS primeiro_ano,
    max(k.ano) AS ultimo_ano,
    list_sort(list_distinct(list(k.ano))) AS anos
FROM cursos k
JOIN classes c ON c.co_cine_rotulo IS NOT DISTINCT FROM k.co_cine_rotulo
WHERE k.tp_nivel_academico = '1'
GROUP BY k.co_cine_rotulo, c.area, c.segmento, c.is_ti, c.regra_nivel, c.regra_codigo,
         c.confianca, c.justificativa
ORDER BY k.co_cine_rotulo
"""

# totais por ano e variação em relação ao ano anterior (função de janela LAG)
SQL_TOTAIS = """
WITH t AS (
    SELECT ano, SUM(matriculas) AS matriculas, SUM(trancadas) AS trancadas,
           SUM(desvinculados) AS desvinculados, SUM(transferidos) AS transferidos,
           SUM(falecidos) AS falecidos
    FROM fato GROUP BY ano
)
SELECT ano, matriculas, trancadas, desvinculados, transferidos, falecidos,
       ano - LAG(ano) OVER w AS distancia,
       trancadas / NULLIF(LAG(trancadas) OVER w, 0) - 1 AS var_trancadas,
       desvinculados / NULLIF(LAG(desvinculados) OVER w, 0) - 1 AS var_desvinculados
FROM t
WINDOW w AS (ORDER BY ano)
ORDER BY ano
"""


def abrir_cursos(con, processados):
    padrao = (processados / "cursos_*.parquet").as_posix()
    con.execute(f"CREATE TEMP VIEW cursos AS SELECT * FROM read_parquet('{padrao}')")


def criar_classes(con):
    """Classifica em Python os rótulos CINE distintos (algumas centenas) e guarda numa tabela."""
    con.execute("""
        CREATE TEMP TABLE classes (
            co_cine_rotulo VARCHAR, area VARCHAR, area_nome VARCHAR, segmento VARCHAR,
            segmento_nome VARCHAR, is_ti BOOLEAN, regra_nivel VARCHAR, regra_codigo VARCHAR,
            confianca VARCHAR, justificativa VARCHAR)
    """)
    linhas = []
    for (rotulo,) in con.execute("SELECT DISTINCT co_cine_rotulo FROM cursos").fetchall():
        c = classificar(rotulo)
        linhas.append([rotulo, c["area"], AREAS[c["area"]], c["segmento"],
                       SEGMENTOS[c["segmento"]], c["is_ti"], c["regra_nivel"],
                       c["regra_codigo"], c["confianca"], c["justificativa"]])
    con.executemany("INSERT INTO classes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", linhas)


def alertas_automaticos(con):
    cur = con.execute(SQL_TOTAIS)
    colunas = [d[0] for d in cur.description]
    totais = [dict(zip(colunas, r, strict=True)) for r in cur.fetchall()]
    alertas = {t["ano"]: [] for t in totais}
    for col in ("matriculas", "trancadas", "desvinculados", "transferidos", "falecidos"):
        positivos = sum(1 for t in totais if (t[col] or 0) > 0)
        for t in totais:
            if t[col] is None:
                alertas[t["ano"]].append(f"{col}: sem informação no ano")
            elif t[col] == 0 and positivos >= 2:
                alertas[t["ano"]].append(
                    f"{col} = 0 no ano, mas positivo nos demais (provável ausência de coleta)"
                )
    for col in ("trancadas", "desvinculados"):
        for t in totais:
            var = t["var_" + col]
            if t["distancia"] == 1 and var is not None and abs(var) > LIMITE_VARIACAO:
                alertas[t["ano"]].append(
                    f"{col}: variação atípica de {var:+.0%} em relação a {t['ano'] - 1}"
                )
    return alertas


def criar_tabela_anos(con, processados, anos):
    con.execute("""
        CREATE TABLE anos (
            ano INTEGER, status VARCHAR, comparabilidade VARCHAR,
            alertas_automaticos VARCHAR[], notas_curadas VARCHAR[], avisos VARCHAR[],
            arquivo_fonte VARCHAR, fonte_last_modified VARCHAR, md5_verificado BOOLEAN,
            processado_em VARCHAR, linhas INTEGER)
    """)
    alertas = alertas_automaticos(con)
    linhas = []
    for ano in sorted(set(anos) | set(alertas)):
        arq = processados / f"cursos_{ano}.json"
        if ano not in alertas or not arq.exists():
            linhas.append([ano, "ausente", None, [], [], [], None, None, None, None, None])
            continue
        info = json.loads(arq.read_text(encoding="utf-8"))
        auto, notas = alertas[ano], NOTAS_CURADAS.get(ano, [])
        linhas.append([
            ano, "disponivel", "atencao" if auto or notas else "comparavel", auto, notas,
            info["avisos"], info["arquivo"], info.get("fonte_last_modified"), info["md5_ok"],
            info.get("processado_em"), info["linhas"],
        ])
    con.executemany("INSERT INTO anos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", linhas)


def consolidar(processados=PROCESSADOS, base=BASE, anos=ANOS):
    if not list(processados.glob("cursos_*.parquet")):
        raise FileNotFoundError("nenhum ano processado (rode: python -m evasao processar)")
    base.parent.mkdir(parents=True, exist_ok=True)
    temp = base.with_suffix(".tmp")
    temp.unlink(missing_ok=True)

    con = duckdb.connect(str(temp))
    try:
        abrir_cursos(con, processados)
        criar_classes(con)
        con.execute(SQL_FATO)
        con.execute(SQL_ROTULOS)
        criar_tabela_anos(con, processados, anos)
        con.execute(
            "CREATE TABLE info AS SELECT ? AS versao_mapeamento, ? AS consolidado_em",
            [VERSAO_MAPEAMENTO, datetime.now().astimezone().isoformat(timespec="seconds")],
        )
        linhas_fato = con.execute("SELECT count(*) FROM fato").fetchone()[0]
        con.execute("CHECKPOINT")
    finally:
        con.close()

    try:
        temp.replace(base)
    except PermissionError as erro:  # no Windows a API aberta trava o arquivo
        raise RuntimeError(f"{base} está em uso; pare a API e rode de novo") from erro
    log.info("base criada em %s (%d linhas na tabela fato)", base, linhas_fato)
    return base


def auditoria(processados=PROCESSADOS, saida=DADOS):
    """Compara o classificador por palavras do notebook com a classificação CINE."""
    con = duckdb.connect()
    abrir_cursos(con, processados)
    criar_classes(con)
    con.execute("CREATE TEMP TABLE legado (no_curso VARCHAR, area_legado VARCHAR)")
    nomes = con.execute("SELECT DISTINCT no_curso FROM cursos").fetchall()
    con.executemany(
        "INSERT INTO legado VALUES (?, ?)", [[n, classificar_como_notebook(n)] for (n,) in nomes]
    )
    con.execute("""
        CREATE TEMP VIEW comparacao AS
        SELECT k.ano, k.co_cine_rotulo, k.no_cine_rotulo, l.area_legado, c.area, c.confianca,
               k.matriculas
        FROM cursos k
        JOIN classes c ON c.co_cine_rotulo IS NOT DISTINCT FROM k.co_cine_rotulo
        JOIN legado l ON l.no_curso IS NOT DISTINCT FROM k.no_curso
        WHERE k.tp_nivel_academico = '1'
    """)
    saida.mkdir(parents=True, exist_ok=True)
    matriz = saida / "auditoria_matriz_legado_x_cine.csv"
    divergencias = saida / "auditoria_divergencias.csv"
    sql_matriz = """
        PIVOT (SELECT area_legado, area, matriculas FROM comparacao)
        ON area USING SUM(matriculas) GROUP BY area_legado ORDER BY area_legado
    """
    con.execute(f"COPY ({sql_matriz}) TO '{matriz.as_posix()}' (HEADER)")
    con.execute(f"""
        COPY (SELECT ano, co_cine_rotulo, no_cine_rotulo, area_legado, area, confianca,
                     SUM(matriculas) AS matriculas
              FROM comparacao WHERE area_legado <> area
              GROUP BY ALL ORDER BY matriculas DESC NULLS LAST)
        TO '{divergencias.as_posix()}' (HEADER)
    """)
    con.sql(sql_matriz).show(max_width=200)
    total, iguais = con.execute(
        "SELECT SUM(matriculas), SUM(matriculas) FILTER (WHERE area_legado = area) FROM comparacao"
    ).fetchone()
    con.close()
    print(f"Mesma área nos dois métodos: {iguais / total:.1%} das matrículas de graduação")
    return matriz, divergencias
