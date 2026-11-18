# Metodologia

Os números do site são calculados por este projeto a partir dos microdados públicos do INEP. **Não são estatísticas oficiais.**

## Dados

- **Fonte:** Microdados do Censo da Educação Superior, de 2009 a 2024 (INEP). <https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-da-educacao-superior>
- **Arquivo usado:** `MICRODADOS_CADASTRO_CURSOS_AAAA.CSV`, dentro do ZIP de cada ano. A integridade de cada CSV foi conferida com o MD5 oficial que vem no próprio ZIP.
- **Escopo:** cursos de graduação (`TP_NIVEL_ACADEMICO = 1`), presenciais e a distância. Os cursos sequenciais ficam de fora.
- **Validação:** a soma de `QT_MAT` da graduação reproduz o total divulgado (2023: 9.976.782; 9.977.217 com os sequenciais).

## Variáveis (Dicionário de Dados do INEP, anexo de cada ZIP)

| Variável | Significado oficial |
|---|---|
| `QT_MAT` | alunos com vínculo **Cursando** ou **Formado** |
| `QT_SIT_TRANCADA` | alunos com matrícula trancada |
| `QT_SIT_DESVINCULADO` | alunos desvinculados do curso |
| `QT_SIT_TRANSFERIDO` | alunos transferidos para outro curso da mesma IES |

Trancamento, desvinculação e evasão são coisas diferentes. A evasão exige acompanhar o mesmo aluno ao longo dos anos, e o INEP a publica nos *Indicadores de Fluxo da Educação Superior*. Este projeto **não calcula evasão**.

## Indicador

**Taxa de trancamento** = `trancadas / (matrículas + trancadas)`

A soma das trancadas no denominador é necessária porque `QT_MAT` não inclui os alunos trancados. Toda agregação, seja por área, período ou curso, soma numeradores e denominadores antes de dividir. Nunca se faz média de porcentagens. Anos sem dados ficam fora da série e nunca aparecem como zero.

A unidade é o **vínculo-ano**, não a pessoa: o mesmo aluno aparece em todos os anos em que esteve vinculado. Por isso o "consolidado do período" não representa número de pessoas.

## Classificação dos cursos

1. Cada curso já vem com o código **CINE Brasil** do INEP, em todos os anos.
2. A tabela [`evasao/mapeamento_cine.csv`](../evasao/mapeamento_cine.csv) liga cada área CINE a uma das 4 áreas do projeto. Cada linha traz a regra, a confiança (alta, média ou baixa) e a justificativa. A regra mais específica prevalece: rótulo → área detalhada → específica → geral.
3. **TI** = área geral CINE 06 (Computação e TIC).
4. Curso sem regra ou sem código fica como **Não classificado**, nunca numa área padrão.

Decisões validadas pelo responsável do projeto em 18/11/2026: licenciaturas seguem a CINE (Educação → Humanas); Direito → Humanas; Economia → Gestão; as subáreas de Serviços ficam distribuídas, com confiança baixa.

## Comparabilidade entre anos

| Ano | Observação | Tratamento |
|---|---|---|
| 2009 | `QT_SIT_TRANSFERIDO` zerado; salto de trancadas (+49%) e desvinculados (+112%) em 2010 | alerta no site |
| 2013 | `TP_REDE` vazio em ~96% das linhas | rede derivada de `TP_CATEGORIA_ADMINISTRATIVA` |
| 2020 | coluna chamada `CO_CINE_ROTULO2` | tratada como `CO_CINE_ROTULO` |
| 2024 | revisão da CINE: códigos de TI renumerados; "Engenharia de computação (DCN Computação)" saiu da área 06 | cursos agregados por nome; quebra de ~2,4% na série de TI |

## Conteúdo de orientação (competências e trilha de estudos)

Cada afirmação das etapas "Competências" e "Estudos" tem fonte, listada em [`web/trilha.json`](../web/trilha.json) e exibida no site com numeração e lista de referências. Fontes usadas:

- **Diretrizes Curriculares Nacionais da Computação** (Resolução CNE/CES nº 5/2016), Arts. 4º e 5º: são a base das cinco competências.
- **Computer Science Curricula 2023** (ACM, IEEE-CS e AAAI) e **Computing Curricula 2020** (ACM e IEEE-CS): currículos de referência internacionais.
- **Wing (2006)**, sobre pensamento computacional; **Dunlosky et al. (2013)**, sobre técnicas de estudo; **Walton e Cohen (2011)**, sobre pertencimento; **Diekelmann e Born (2010)**, sobre sono e memória; **Guo (2013)**, sobre o Python Tutor.
- **LDB** (Lei nº 9.394/1996, art. 84, monitoria), **PNAES** (Lei nº 14.914/2024), **ProUni** (Lei nº 11.096/2005) e **FIES** (Lei nº 10.260/2001).

Os DOIs foram conferidos no Crossref e os textos legais na fonte oficial em 18/11/2026. A ordem das etapas da trilha e os momentos sugeridos ("antes do curso", "primeiro semestre") são uma **sugestão do projeto**, baseada no princípio de começar pelos fundamentos, e não uma norma.

## Formulário vocacional

O formulário atual é **fictício** e serve só para demonstrar o fluxo. A pontuação provisória soma os pesos declarados no próprio HTML e é sempre identificada como demonstração. O site é uma ferramenta de orientação, não um diagnóstico psicológico.

## Privacidade

O site não coleta dados pessoais. As respostas do formulário ficam apenas no `sessionStorage` do navegador e são apagadas quando a aba é fechada.
