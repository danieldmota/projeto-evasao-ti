# Etapa 1: Auditoria do notebook `Untitled3.ipynb`

Data: 18/11/2026. A auditoria leu o notebook inteiro e usou os **arquivos oficiais do INEP de 2009 a 2024**, baixados e verificados por MD5. Todo achado abaixo foi testado nos dados reais. Os números citados foram calculados por este projeto e **não são estatísticas oficiais do INEP**.

## 1. O que o notebook faz

| Célula | Ação |
|---|---|
| 1 | Monta o Google Drive e tenta extrair `INEP/top.zip`. No output salvo, **o arquivo não existe** (célula sem efeito). |
| 3 | Lê `MICRODADOS_CADASTRO_CURSOS_*.CSV` do Drive. Escolhe colunas por **correspondência parcial** e classifica os cursos por **palavras-chave em `NO_CURSO`**. Calcula `trancadas / (matriculadas + trancadas)` por área e ano. |
| 5 | Gera um gráfico de barras por ano: `pivot_table(aggfunc="mean").fillna(0)`. |
| 7 | **Lê todos os arquivos de novo**, soma os 16 anos e gera o gráfico "Porcentagem de pessoas que trancaram cursos nos últimos 16 anos". |

Colunas efetivamente usadas: `NO_CURSO` (via `'NO_CURSO' in col`), `QT_SIT_TRANCADA` (via `'QT_SIT_TRANCADA' in col`) e `QT_MAT` (primeira coluna que contém `'QT_MAT'`).

**Verificação cruzada:** reimplementei a lógica do notebook (função `classificar_como_notebook` em [classificacao.py](../evasao/classificacao.py)) e rodei sobre os CSVs oficiais. O resultado bate **exatamente** com o output salvo de 2009 (Exatas 7,86%, Saúde 4,83%, Gestão 8,51%, Humanas 6,91%). Isso confirma que o notebook usou esses mesmos arquivos.

## 2. Problemas encontrados

### 2.1 Classificação (grave)
- **16,5% das matrículas-ano de 2009–2024 (21,4 milhões) caem na área errada** quando comparadas com a CINE. Divergências principais:

| Curso (rótulo CINE) | Notebook | CINE (projeto) | Matrículas-ano afetadas |
|---|---|---|---|
| Educação física (bacharelado) | Exatas | Natureza e Saúde | 2,42 mi |
| Educação física (licenciatura) | Exatas | Humanas (Educação) | 2,11 mi |
| Arquitetura e urbanismo | Humanas | Exatas | 1,99 mi |
| Matemática (licenciatura) | Exatas | Humanas (Educação) | 1,34 mi |
| Agronomia | Humanas | Natureza e Saúde | 1,23 mi |
| Economia ("Ciências Econômicas") | Humanas | Gestão e Negócios | 0,88 mi |
| Biologia ("Ciências Biológicas") | Humanas | Natureza e Saúde | 0,51 mi |

- Causas: (a) a ordem dos testes, já que `"física"` (Exatas) é testada antes de `"educação física"`; (b) palavras que não aparecem no nome oficial, como `"biologia"`, que não casa com "Ciências Biológicas"; (c) **qualquer curso não reconhecido, inclusive nome ausente, vai para Humanas**.
- A CINE estava disponível em **todos os anos** (`CO_CINE_ROTULO`, `CO_CINE_AREA_*`) e não foi usada.
- Não havia auditoria dos resultados da classificação.

Relatório completo: `python -m evasao auditoria`.

### 2.2 Indicador
- **O denominador `QT_MAT + QT_SIT_TRANCADA` está correto e foi mantido.** Segundo o dicionário oficial, `QT_MAT` = vínculos "Cursando e/ou Formado" e **não inclui** trancados. Detalhes em [metodologia.md](metodologia.md).
- O título "porcentagem de **pessoas** que trancaram nos últimos 16 anos" está **errado**. A soma de 16 anos conta vínculos-ano: o mesmo aluno aparece em cada ano em que esteve vinculado. Os microdados públicos não permitem identificar pessoas.
- `fillna(0)` no gráfico anual faz um ano ou área sem dados aparecer como **0% de trancamento**.
- `denom.replace(0, 1)` esconde denominadores zero (resulta em taxa 0 em vez de "indefinida").
- `pd.to_numeric(errors="coerce").fillna(0)` transforma valores inválidos e nulos em zero sem avisar.
- Os cursos **sequenciais** (`TP_NIVEL_ACADEMICO = 2`) entravam junto com a graduação.

### 2.3 Processamento
- Os mesmos arquivos são lidos duas vezes (células 3 e 7).
- Caminhos fixos do Colab/Drive (`/content/drive/MyDrive/INEP`).
- A seleção de colunas por correspondência parcial é frágil: `'QT_MAT' in col` aceitaria `QT_MAT_FEM` se `QT_MAT` faltasse.
- `except Exception: pass` na célula 7 descarta anos inteiros sem aviso.
- Os valores absolutos não são preservados (só a taxa sai da célula 3), e não existe base consolidada reutilizável.
- O ano é extraído do nome do arquivo, não de `NU_ANO_CENSO`.

## 3. O que os arquivos oficiais revelaram (o notebook não percebia)

| Ano | Achado | Tratamento |
|---|---|---|
| todos | Linhas EaD repetidas por município (`TP_DIMENSAO=2`). A linha "nível Brasil" (`TP_DIMENSAO=3`) só traz `QT_CURSO`. | A soma de todas as linhas reproduz os totais oficiais. Nulos são preservados, nunca viram zero. |
| todos | `CO_CINE_ROTULO` vem entre aspas triplas (Nota INEP de 01/11/2022). | Aspas removidas. |
| 2009 | `QT_SIT_TRANSFERIDO = 0` em todos os cursos. Trancadas +49% e desvinculados +112% em 2010. | Alerta de comparabilidade. |
| 2013 | `TP_REDE` vazio em ~96% das linhas. | Derivado de `TP_CATEGORIA_ADMINISTRATIVA` (relação verificada como determinística em 2012, 2014 e 2024). |
| 2020 | A coluna se chama `CO_CINE_ROTULO2`. | Alias explícito. Uma busca parcial poderia pegar a coluna errada sem perceber. |
| 2023 | ZIP com outra pasta raiz e outra codificação nos nomes. CSV de 390 MB. | O CSV é localizado pelo nome do arquivo, e a leitura é feita em blocos. |
| 2024 | **Revisão da CINE**: os códigos de TI foram reorganizados, e "Engenharia de computação (DCN Computação)" e "Sistemas embarcados" saíram da área 06. | Agregação por nome do curso. Quebra documentada (cerca de 2,4% das matrículas de TI de 2023). |

Totais de matrícula de graduação recalculados (validação do pipeline): 2009 = 5.954.021, 2016 = 8.048.701, 2023 = **9.976.782** (este último confere com o valor publicado em fontes que citam o INEP), 2024 = 10.226.873.
