# Evasão em TI

Projeto da disciplina de Big Data. Processa os microdados do **Censo da Educação Superior (INEP), de 2009 a 2024**, calcula a taxa de trancamento de matrícula por área de conhecimento, com destaque para TI, e publica um site com uma jornada de orientação vocacional.

> Os números são calculados a partir dos microdados públicos do INEP e **não** são estatísticas oficiais.

## Estrutura

```
evasao/        pipeline de dados e API
  coleta.py          baixa os ZIPs do INEP e confere o MD5 oficial
  processamento.py   lê os CSVs em blocos e grava um Parquet por ano
  classificacao.py   classifica os cursos pela CINE Brasil (mapeamento_cine.csv)
  consolidacao.py    monta a base DuckDB com SQL (dados/evasao.duckdb)
  api.py             API FastAPI que também serve o site
web/           site: jornada guiada (index.html) e painel de dados (estatisticas.html)
testes/        testes com pytest
docs/          metodologia e auditoria do notebook original
```

Fluxo dos dados: **ZIP do INEP → Parquet por ano → DuckDB → API → site**.

## Como rodar

Requisitos: Python 3.12+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |    macOS/Linux: source .venv/bin/activate
pip install -e ".[pipeline,dev]"
```

O repositório já traz a base consolidada (`dados/evasao.duckdb`), então dá para abrir o site direto:

```bash
python -m evasao api        # site e API em http://127.0.0.1:8000  (documentação em /docs)
```

Para refazer tudo a partir dos dados do INEP (cerca de 650 MB de download):

```bash
python -m evasao baixar --anos 2009-2024
python -m evasao processar --anos 2009-2024
python -m evasao consolidar
python -m evasao auditoria   # compara a classificação do notebook com a CINE
```

## Testes

```bash
pytest
```

Os testes de dados reais só rodam se os ZIPs estiverem em `dados/brutos/`.

## Principais endpoints

| Rota | O que retorna |
|---|---|
| `/api/v1/statistics/annual?group_by=segmento` | taxa de trancamento por ano e área |
| `/api/v1/statistics/summary` | consolidado do período |
| `/api/v1/statistics/courses?q=computacao` | indicadores por curso |
| `/api/v1/years` | anos disponíveis e alertas de comparabilidade |
| `/api/v1/methodology` | metodologia |

Filtros: `year_start`, `year_end`, `area`, `ti`, `modalidade` (`presencial`/`ead`), `rede` (`publica`/`privada`).

## Formulário vocacional

O formulário em `web/formulario.html` é **fictício** e só demonstra o fluxo. Quando o formulário oficial ficar pronto, basta substituir esse arquivo:

- cada `<fieldset>` vira uma tela da jornada, com a pergunta no `<legend>`;
- cada campo precisa de `name`, e a validação usa os atributos normais do HTML (`required`, `min`, `max`);
- a pontuação provisória usa `data-pesos="AREA:peso"` nas opções. Para usar um algoritmo próprio, mude `pontuacao` para `"api"` no início de `web/index.html`.

O site não coleta dados pessoais.

## Deploy

Publicado na Vercel. O `pyproject.toml` aponta a aplicação (`evasao.api:app`), e a Vercel serve a API e o site no mesmo endereço.

## Documentação

- [docs/metodologia.md](docs/metodologia.md): dados, indicador, classificação, comparabilidade e **fontes** do conteúdo de orientação
- [docs/auditoria_notebook.md](docs/auditoria_notebook.md): problemas encontrados no notebook original do Colab
