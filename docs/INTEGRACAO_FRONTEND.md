# Integração com o frontend e com o futuro formulário vocacional

## 1. Consumindo as estatísticas (seções 6 e 7 do site)

Base: `https://<host>/api/v1`. Documentação interativa: `/docs` (Swagger) e `/redoc`.

Todas as respostas seguem o formato `{ "data": [...], "meta": {...} }`. O campo `meta` traz fonte, unidade, escopo, método, período (`anos_com_dados`, `anos_ausentes`), versão do mapeamento, data do build, filtros aplicados e **avisos**. **Exiba `meta.avisos` e `meta.fonte.nota` perto dos gráficos.**

| Uso no site | Chamada |
|---|---|
| Gráfico anual por área | `GET /statistics/annual?group_by=area` |
| Gráfico anual com TI separada | `GET /statistics/annual?group_by=segmento` |
| Barra consolidada (destaque Exatas/TI) | `GET /statistics/summary?group_by=segmento` |
| TI presencial × EaD | `GET /statistics/summary?ti=true&modalidade=ead` (e `presencial`) |
| Cursos de TI com mais matrículas | `GET /statistics/courses?ti=true&year_start=2024&limit=10` |
| Busca de curso | `GET /statistics/courses?q=computacao` (ignora acentos) |
| "De onde vêm os números?" | `GET /methodology`, `GET /years` |

Filtros comuns: `year_start`, `year_end`, `area` (repetível), `segmento`, `ti`, `modalidade` (`presencial`/`ead`), `rede` (`publica`/`privada`), `cine_geral`.

Regras de apresentação:
- `taxa_*` é uma proporção de 0 a 1. Multiplique por 100 para exibir em %.
- `null` significa **sem dado**. Não desenhe como zero; deixe uma lacuna na série.
- No consolidado, use o rótulo "vínculos-ano", nunca "pessoas".
- Para cursos com `base_pequena: true`, omita ou sinalize a taxa (é instável).

Exemplo (JavaScript):
```js
const r = await fetch(`${API}/statistics/annual?group_by=segmento&year_start=2014`);
const { data, meta } = await r.json();
// data: [{ano, grupo_codigo, grupo_nome, matriculas, trancadas, taxa_trancamento, ...}]
```

CORS: configure `EVASAO_CORS_ORIGINS` com o domínio do site. A API aceita só `GET`.

### Página de referência: `web/estatisticas.html`
Página estática (HTML + JS puro, sem dependências) que implementa a seção 6 do site: indicadores do último ano, série anual por área com TI em destaque, consolidado do período, tabelas acessíveis, alertas de comparabilidade e notas de leitura. Tem filtros de período, modalidade e rede, modo claro/escuro e layout para celular.

```bash
evasao-ti serve                                            # API em 127.0.0.1:8000
python -m http.server 5173 --bind 127.0.0.1 --directory web
# abra http://localhost:5173/estatisticas.html
```
Para outra API: `estatisticas.html?api=https://minha-api/api/v1`. A origem da página precisa estar em `EVASAO_CORS_ORIGINS`. Abrir o arquivo direto (`file://`) não funciona por causa do CORS.

### Seções 7 e 8: `web/trilha-ti.html`
Cinco competências de TI e recomendações de estudo para iniciantes. O texto fica em [`web/conteudo/trilha-ti.json`](../web/conteudo/trilha-ti.json), fonte única que o site definitivo também pode consumir. Para editar o conteúdo, altere só o JSON, incremente `versao` e atualize `revisado_em`. O teste `tests/test_conteudo.py` garante a estrutura: exatamente 5 competências, recursos referenciados existentes, links https e materiais gratuitos. Antes de cada publicação, confira se os links externos continuam no ar.

As duas páginas compartilham o tema em `web/assets/tema.css`. A linguagem visual é editorial ("papel e tinta"): títulos em *Newsreader* e texto em *Atkinson Hyperlegible*, fonte desenhada para legibilidade, carregadas do Google Fonts com fallback local. O seletor **Auto / Claro / Escuro** (`web/assets/tema.js`) segue o sistema por padrão e guarda a escolha no navegador. O script vai no `<head>` para aplicar o tema antes da primeira pintura. As cores dos gráficos são validadas contra os dois fundos. "Permanência em TI" é um nome provisório, que deve ser trocado pelo nome oficial do projeto.

Elas servem de referência visual e de contrato. Quando o site definitivo existir, os gráficos podem ser portados para o framework escolhido, mantendo as mesmas chamadas e regras de apresentação.

## 2. Jornada guiada e formulário vocacional

A jornada completa das 8 etapas está em [`web/index.html`](../web/index.html) e funciona com um formulário **fictício**. O passo a passo para encaixar o HTML oficial está em [INTEGRACAO_FORMULARIO.md](INTEGRACAO_FORMULARIO.md). No servidor, as rotas abaixo ainda **não existem**: a jornada roda em modo demonstração até que sejam implementadas e configuradas em `JORNADA_CONFIG`.

Rotas planejadas (etapas 2 a 5 do site):

| Passo | Rota planejada | Contrato | Dados pessoais? |
|---|---|---|---|
| Enviar respostas | `POST /api/v1/vocational/submissions` | `VocationalSubmission` → `VocationalResult` | Não (só `session_id` aleatório) |
| Interesse em TI | `POST /api/v1/vocational/it-interest` | `ItInterestRecord` (`sim`/`nao`/`talvez`) | Não |
| Participar do projeto | `POST /api/v1/participation` | `ProjectParticipation` com `Consent` | **Sim** (nome, e-mail) |

Para implementar quando o HTML estiver disponível:
1. Mapear cada campo do formulário para um `question_id` estável e versionar o questionário (`questionnaire_version`).
2. Definir o algoritmo de pontuação em um módulo próprio (`vocational/scoring.py`), com `scoring_version` e testes. Os códigos de área do teste são do questionário e **não** precisam coincidir com as áreas INEP.
3. Sempre devolver o `disclaimer`: orientação, não diagnóstico psicológico.
4. Persistência: nesse momento entra o **PostgreSQL** (serviço separado do warehouse estatístico), com migrações (Alembic).
5. Proteção contra abuso: rate limiting e captcha no formulário de participação.

## 3. LGPD (planejamento)
| Princípio | Aplicação |
|---|---|
| Finalidade | `purpose_code` explícito (ex.: contato do projeto de prevenção da evasão). Os dados não são usados para outro fim. |
| Minimização | Teste e interesse em TI são anônimos. Participação coleta só nome e e-mail. Nada de CPF, endereço ou data de nascimento. |
| Base legal | Consentimento (art. 7º, I), livre e específico, com `privacy_policy_version` e `granted_at` registrados. |
| Transparência | Política de privacidade publicada e versionada, com link no formulário. |
| Direitos do titular | Canal para acesso, correção, eliminação e revogação do consentimento. A revogação apaga o contato. |
| Segurança | HTTPS, banco com acesso restrito, e-mails em coluna protegida, logs **sem** dados pessoais (os logs atuais não registram nenhum). |
| Retenção | Sugestão: respostas anônimas por até 2 anos para análise agregada. Contatos até o fim do projeto ou até a revogação, com exclusão automática agendada. |
| Menores de idade | Se o público incluir menores de 18 anos, exigir consentimento do responsável (art. 14) ou não coletar contato. |

A separação é estrutural: o pacote `vocational` não importa nada das estatísticas, e as estatísticas não dependem dele.
