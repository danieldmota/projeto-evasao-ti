# Metodologia, limitações e fontes

> Os números produzidos por este projeto são **calculados a partir dos microdados públicos do INEP**. Eles **não** são estatísticas oficiais publicadas pelo INEP.

## Fontes
- **Microdados do Censo da Educação Superior** (um ZIP por ano):
  https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-da-educacao-superior
  Padrão confirmado: `https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_{ano}.zip`
- **Dicionário de Dados**: arquivo `ANEXO I` dentro de cada ZIP (aba `cadastro_cursos`).
- **Nota informativa INEP de 01/11/2022**: `TP_DIMENSAO` e aspas em `CO_CINE_ROTULO`.
- **CINE Brasil**: https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/cine-brasil

## Escopo
Inclui cursos de **graduação** (`TP_NIVEL_ACADEMICO = 1`), presenciais e EaD, de todas as redes e das quatro dimensões (`TP_DIMENSAO` 1 a 4). Os sequenciais de formação específica ficam de fora.

## Conceitos (dicionário oficial)
| Termo | Variável | Definição oficial / observação |
|---|---|---|
| Matrícula | `QT_MAT` | "Soma do número de alunos com situação de vínculo ao curso igual a: **Cursando e/ou Formado**" |
| Trancamento | `QT_SIT_TRANCADA` | "alunos com situação de vínculo no curso: matrícula trancada" |
| Desvinculação | `QT_SIT_DESVINCULADO` | "aluno desvinculado do curso". Não distingue abandono, desistência formal etc. |
| Transferência | `QT_SIT_TRANSFERIDO` | para outro curso da mesma IES |
| Evasão / desistência | não disponível | Exige acompanhar coortes. O INEP publica isso nos *Indicadores de Fluxo da Educação Superior*. **Este projeto não calcula evasão.** |
| Abandono | não disponível | Não há variável correspondente no arquivo de cursos. |

## Indicadores
Unidade: **vínculo aluno-curso no ano de referência** (não pessoa).

| Indicador | Fórmula |
|---|---|
| `taxa_trancamento` | `trancadas / (matriculas + trancadas)` |
| `participacao_trancadas_vinculos` | `trancadas / (matriculas + trancadas + desvinculados + transferidos + falecidos)` |
| `taxa_desvinculacao` | `desvinculados / (mesmo denominador acima)`, indicador complementar, **não** é evasão oficial |

**Por que o denominador do notebook foi mantido:** `QT_MAT` não contém trancados. Para obter uma proporção entre 0 e 1 é preciso somar as trancadas ao denominador. Limitação: o denominador inclui os *formados* no ano.

**Agregação:** sempre por razão de somas (somam-se numeradores e denominadores, depois divide-se). Nunca se calcula a média de percentuais. Um grupo sem informação fica `null`, nunca `0`. A taxa é `null` quando o denominador é 0. Anos sem dados ficam fora da série e aparecem em `meta.periodo.anos_ausentes`.

**Consolidado do período:** é a soma de vínculos-ano. A pergunta que ele responde é "qual fração dos vínculos-ano observados estava trancada", e **não** "quantas pessoas trancaram".

## Classificação

1. **CINE Brasil** (oficial, presente em todos os anos): rótulo (7 caracteres) → área detalhada (4) → específica (3) → geral (2).
2. **4 áreas do projeto**: correspondência própria em [`cine_area_mapping.csv`](../src/evasao_ti/classification/data/cine_area_mapping.csv). Cada linha tem nível, código, área, **confiança** (alta/média/baixa) e **justificativa**. A regra mais específica prevalece.
3. **TI** = CINE área geral **06** (Computação e TIC). Com isso, TI é um subconjunto separável de Exatas (segmento `TI` × `EXATAS_EXCETO_TI`).
4. **Sem regra ou sem código CINE válido → `NAO_CLASSIFICADO`**, nunca uma área padrão. A Área Básica de Ingresso (ABI, CINE 001) também é tratada como não classificada.

Decisões contestáveis (todas documentadas no CSV):
- Licenciaturas (inclusive Matemática, Física e Computação) seguem a CINE (Educação), ou seja, vão para **Humanas**, não para Exatas/TI.
- Direito → Humanas (a CINE coloca em Negócios). Economia → Gestão (a CINE coloca em Ciências sociais). Ambas seguem a narrativa original do projeto.
- A área geral 10 (Serviços) não tem equivalente direto. Cada área detalhada recebeu uma área com confiança **baixa**. A API informa a fração de matrículas nessa situação (~2,3%).

### Histórico de versões do mapeamento
| Versão | Data | Mudança |
|---|---|---|
| 1.0.0 | 18/11/2026 | Versão inicial (áreas específicas e detalhadas observadas em 2009–2023) |
| 1.1.0 | 18/11/2026 | Regra para o código transitório `049` (surge em 2024) |

**Validação do responsável pelo projeto (18/11/2026):** confirmadas as três decisões contestáveis: licenciaturas seguem a CINE (Educação → Humanas); Direito → Humanas e Economia → Gestão; subáreas de Serviços distribuídas entre as 4 áreas com confiança "baixa", com o percentual informado pela API.

Ao alterar o CSV: incremente `MAPPING_VERSION` em `mapping.py`, registre a mudança aqui e rode `evasao-ti build`.

## Comparabilidade 2009–2024
- A série 2009–2020 foi republicada pelo INEP em 04/11/2022 no layout atual, com CINE atribuída retroativamente.
- Alertas automáticos (coluna zerada, variação anual acima de 40%) e notas curadas por ano: `GET /api/v1/years`. Resumo: **2009** (transferidos zerados), **2010** (saltos em relação a 2009), **2013** (rede derivada), **2020** (pandemia; nome de coluna), **2024** (revisão CINE com quebra de TI).
- Mudanças de códigos CINE por ano: `GET /api/v1/classification/changes`.

## Limitações
- Não há identificação de pessoas: não dá para contar estudantes únicos nem acompanhar trajetórias.
- Trancamento é declarado pela IES. A qualidade varia entre instituições e anos.
- Os resultados por área dependem da correspondência do projeto (versionada e auditável), que não é oficial.
- O teste vocacional da plataforma é uma ferramenta de orientação, **não** um diagnóstico psicológico validado.
