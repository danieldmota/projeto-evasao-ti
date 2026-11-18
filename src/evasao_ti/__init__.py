"""Pipeline de dados do Censo da Educação Superior (INEP) e API REST.

Camadas:
- acquisition: descoberta de URLs oficiais, download e validação dos ZIPs;
- processing: leitura eficiente dos CSVs, validação de schema e padronização;
- classification: classificação auditável via CINE Brasil + correspondência versionada;
- analytics: indicadores com numeradores/denominadores consolidados;
- storage: Parquet por ano (staging) e DuckDB (warehouse) consultado pela API;
- api: FastAPI somente leitura sobre dados previamente consolidados;
- vocational: contratos (sem algoritmo) para o futuro formulário vocacional.
"""

__version__ = "0.1.0"
