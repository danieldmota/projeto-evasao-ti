# Arquitetura e decisões

```
 INEP (download.inep.gov.br)
        │  evasao-ti download   (HEAD → ETag/tamanho, .part, MD5 oficial, retentativas)
        ▼
 data/raw/*.zip + downloads.json
        │  evasao-ti ingest     (lê o CSV direto do ZIP, em blocos, só as colunas necessárias)
        ▼
 data/staging/cursos_AAAA.parquet + .meta.json   (1 por ano, nível curso, proveniência + qualidade)
        │  evasao-ti build      (classificação CINE → áreas; agregações; alertas)
        ▼
 data/warehouse/evasao_ti.duckdb   (somente leitura para a API)
        │  evasao-ti serve
        ▼
 FastAPI /api/v1/*  ──►  frontend
```

## Módulos (`src/evasao_ti/`)
| Pacote | Responsabilidade |
|---|---|
| `acquisition/` | URLs oficiais (`sources`), cliente TLS (`http`), download idempotente (`download`), validação de ZIP e MD5 (`archive`) |
| `processing/` | schema explícito e aliases (`schema`), leitura em blocos e validação (`reader`) |
| `classification/` | áreas e segmentos, mapeamento CINE versionado, auditoria contra o notebook (`legacy`, `audit`) |
| `analytics/` | indicadores (razão de somas), consultas, comparabilidade, metodologia |
| `storage/` | staging Parquet, construção do DuckDB, repositório de leitura |
| `api/` | app FastAPI, rotas, schemas, tratamento de erros, CORS |
| `vocational/` | **apenas contratos** (Pydantic). Isolado das estatísticas. |

## Decisões
- **Pandas + Parquet + DuckDB, sem PostgreSQL.** Os dados públicos são somente leitura e pequenos depois de agregados (cerca de 46 mil cursos por ano). Um arquivo DuckDB se distribui junto com a aplicação e não exige servidor. O PostgreSQL só se justifica quando houver gravação (formulários e inscrições), e nesse momento ele fica em um serviço separado.
- **Staging por ano.** Atualizar um ano não reprocessa os outros. O reprocessamento só acontece quando o SHA-256 da fonte ou `STAGING_SCHEMA_VERSION` mudam.
- **Classificação aplicada no build, não na ingestão.** Mudar o mapeamento exige só `evasao-ti build` (segundos), sem reler os CSVs.
- **Schema por nome exato.** Diferenças anuais são declaradas (`COLUMN_ALIASES`, `CATEGORIA_TO_REDE`), nunca adivinhadas por correspondência parcial.
- **A API não acessa a rede.** Ela carrega as tabelas do DuckDB em memória, recarrega quando o arquivo muda e fecha a conexão logo depois. Assim um novo build pode substituir o arquivo com a API no ar (no Windows, se der erro, pare a API).
- **TLS sempre verificado.** O servidor do INEP envia a cadeia de certificados incompleta. A solução é o `truststore` (repositório de certificados do SO) ou `EVASAO_CA_BUNDLE`, nunca `verify=False`.
- **Logs em JSON por linha** (stdlib) com contexto (`ano`, `arquivo`, `erro`), prontos para coletores.

## Operação
- Atualização anual: `evasao-ti update --years 2025` seguido de reiniciar ou recarregar a API (a recarga é automática).
- Implantação: a API só precisa de `data/warehouse/evasao_ti.duckdb`. Gere-o no CI ou em um job e copie para o servidor. Os microdados não precisam ir para lá.
- Exemplo: `uvicorn evasao_ti.api.app:create_app --factory --host 0.0.0.0 --port 8000 --workers 2` atrás de um proxy reverso (HTTPS).
