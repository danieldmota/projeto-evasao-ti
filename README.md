# evasao-ti: dados do INEP para orientação vocacional e prevenção da evasão em TI

Pipeline e API REST que baixam, validam e consolidam os **Microdados do Censo da Educação Superior (INEP)** de 2009 a 2024. Os cursos são classificados pela **CINE Brasil**, e a API serve os indicadores de matrícula e trancamento para o site da plataforma.

> Os números são calculados por este projeto a partir dos microdados públicos. Eles **não** são estatísticas oficiais do INEP.

Documentação:
- [docs/AUDITORIA_NOTEBOOK.md](docs/AUDITORIA_NOTEBOOK.md): diagnóstico do notebook original
- [docs/METODOLOGIA.md](docs/METODOLOGIA.md): definições, fórmulas, classificação, limitações e fontes
- [docs/ARQUITETURA.md](docs/ARQUITETURA.md): estrutura e decisões técnicas
- [docs/INTEGRACAO_FRONTEND.md](docs/INTEGRACAO_FRONTEND.md): consumo da API, contratos do formulário vocacional e LGPD

## Requisitos
- Python **3.12+**
- ~1 GB livre em disco para a série completa (o ZIP de 2024 tem 457 MB, os demais de 5 a 40 MB)
- Opcional: [uv](https://docs.astral.sh/uv/) (mais rápido que pip)

## Instalação

**Windows (PowerShell)**
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

**macOS / Linux**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Com uv (qualquer sistema): `uv venv --python 3.12 && uv pip install -e ".[dev]"`.

## Uso

```bash
evasao-ti discover                    # confere as URLs na página oficial do INEP
evasao-ti update --years 2009-2024    # download + ingestão + build (idempotente)
evasao-ti report --group-by segmento  # série anual no terminal
evasao-ti audit                       # CINE × lógica do notebook → data/reports/
evasao-ti serve                       # API em http://127.0.0.1:8000/docs
```

Etapas separadas: `download`, `ingest`, `build`. Para atualizar só um ano: `evasao-ti update --years 2025`.

**Só com um CSV local** (sem download), por exemplo um arquivo antigo do Drive:
```bash
evasao-ti ingest-csv caminho/MICRODADOS_CADASTRO_CURSOS_2023.CSV
evasao-ti build
```

### Certificado TLS do INEP
O servidor `download.inep.gov.br` envia a cadeia de certificados incompleta. Por isso o projeto usa `truststore`, que valida com o repositório do sistema (funciona no Windows e no macOS). Em **Linux**, se aparecer `CERTIFICATE_VERIFY_FAILED`, aponte `EVASAO_CA_BUNDLE` para um PEM que contenha o intermediário *RNP ICPEdu GR46 OV TLS CA 2025*, obtido da URL AIA do certificado. **Não desative a verificação.**

## Endpoints
| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/v1/health` | estado, versão e anos disponíveis |
| GET | `/api/v1/areas` | áreas, segmentos (TI separada) e regras de correspondência |
| GET | `/api/v1/years` | status, proveniência e comparabilidade por ano |
| GET | `/api/v1/statistics/annual` | série anual por área/segmento/CINE |
| GET | `/api/v1/statistics/summary` | consolidado do período (razão de somas) |
| GET | `/api/v1/statistics/courses` | indicadores por curso (nome CINE), paginado |
| GET | `/api/v1/classification/rotulos` | classificação de cada rótulo CINE, com regra e confiança |
| GET | `/api/v1/classification/changes` | códigos CINE que surgem ou somem por ano |
| GET | `/api/v1/methodology` | metodologia estruturada |

## Testes e qualidade
```bash
pytest                    # unitários + integração (fixtures sintéticas) + dados reais, se presentes
pytest -m "not real_data" # só fixtures sintéticas
ruff check src tests && ruff format --check src tests
```
As fixtures em `tests/synthetic.py` são **fictícias** e servem só para testar o código. Os testes `real_data` usam os ZIPs em `data/raw/` e são pulados se eles não existirem.

## Configuração (`.env`)
Veja [.env.example](.env.example): `EVASAO_DATA_DIR`, anos esperados, URL oficial, `EVASAO_CA_BUNDLE`, `EVASAO_CORS_ORIGINS`, logs (`json`/`text`).

## Estrutura
```
src/evasao_ti/   acquisition/ processing/ classification/ analytics/ storage/ api/ vocational/ cli.py
tests/           testes + gerador de fixtures sintéticas
docs/            auditoria, metodologia, arquitetura, integração
data/            (fora do Git) raw/ staging/ warehouse/ reports/
```
