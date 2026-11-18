# Como encaixar o formulário oficial na jornada

A jornada guiada ([`web/index.html`](../web/index.html)) já está pronta e funciona de ponta a ponta com um **formulário fictício** ([`web/formulario/formulario.html`](../web/formulario/formulario.html)). Quando o HTML oficial chegar, basta substituir esse arquivo. Nada no código da jornada precisa mudar.

## As 8 etapas

| # | Etapa | O que acontece | Avança quando |
|---|---|---|---|
| 1 | Boas-vindas | Explica o que vem pela frente (Responda → Descubra → Planeje) | "Começar" |
| 2 | Formulário | Cada `<fieldset>` vira uma tela, com progresso "Pergunta X de N" | todas as telas são válidas |
| 3 | Resultado | Áreas de afinidade em ordem, com barras animadas | sempre |
| 4 | Interesse em TI | Sim / Talvez / Não, com texto adaptado ao resultado | uma opção é escolhida |
| 5 | Convite ao projeto | Nome, e-mail e consentimento (LGPD), ou "Agora não" | a pessoa decide |
| 6 | Dados | Trancamento por área (API INEP), com destaque de TI e da área de afinidade | sempre |
| 7 | Competências | 5 competências em acordeão | sempre |
| 8 | Estudos | Trilha em etapas, hábitos e "Pensando em trancar?" | "Concluir jornada" |
| ✓ | Fim | Resumo da jornada e opção de apagar as respostas | — |

Não é possível pular etapas obrigatórias: abrir `#/dados` direto, por exemplo, leva de volta à etapa mais avançada permitida. O botão voltar do navegador funciona, e recarregar a página mantém o progresso. Celular: progresso no topo e ações fixas no rodapé. Desktop: trilha das etapas na lateral.

## Passo a passo do encaixe

1. **Salve o HTML oficial** como `web/formulario/formulario.html` (ou outro nome, ajustando `formulario` em `JORNADA_CONFIG` dentro de `index.html`).
2. **Confira o contrato** (também descrito no topo do arquivo fictício):
   - um único `<form>`, opcionalmente com `data-questionnaire-id` e `data-questionnaire-version`;
   - cada `<fieldset>` direto do form vira uma tela, com a pergunta no `<legend>` e, se quiser, ajuda em `<p class="ajuda">`;
   - todo campo tem `name` (vira `question_id`) e usa a validação HTML normal (`required`, `min`, `max`, `maxlength`). `data-erro` personaliza a mensagem;
   - grupos de checkbox aceitam `data-min` e `data-max` no `<fieldset>`;
   - escalas usam `<input type="range">`, com `data-rotulo-min` e `data-rotulo-max` para as pontas;
   - sem `<script>` e sem atributos `on*`: ambos são removidos ao carregar.
3. **Escolha como pontuar** (`pontuacao` em `JORNADA_CONFIG`):
   - `"pesos"`: cada opção declara `data-pesos="AREA:peso, ..."`. É provisório, e a tela de resultado mostra o aviso de demonstração;
   - `"api"`: a jornada envia `VocationalSubmission` para `POST {api}/vocational/submissions` e exibe o `VocationalResult` retornado (contratos em [`vocational/contracts.py`](../src/evasao_ti/vocational/contracts.py)). É o caminho para o algoritmo oficial.
4. **Áreas diferentes das 5 áreas dos dados?** Preencha `areas` (códigos e nomes do questionário) e `mapaAreasParaDados` (ex.: `{"computacao": "TI"}`), para que a etapa 6 destaque a área certa nos gráficos.
5. **Ative os envios** quando o servidor existir: `endpoints.interesse` e `endpoints.participacao`. Enquanto forem `null`, a tela informa "modo demonstração: nada foi enviado".
6. **Edite os textos do convite** em `projeto` (descrição, finalidade, retenção, link e versão da política de privacidade), todos marcados `[EDITAR]`.
7. **Teste:** `pytest -m e2e` percorre a jornada inteira em Chrome real. Se o formulário oficial tiver outras perguntas, ajuste `_answer_form` em [`tests/e2e/test_jornada.py`](../tests/e2e/test_jornada.py).

## Privacidade (LGPD)
- As respostas do teste ficam só no `sessionStorage` da aba (somem ao fechá-la) e não carregam identificação. A tela final oferece "Apagar agora".
- **Nome e e-mail nunca são gravados no navegador.** Vão direto para o endpoint de participação (quando configurado) e o formulário é limpo em seguida. Isso tem teste automatizado.
- A inscrição não é ligada às respostas do teste (`session_id: null`), por minimização.
- O consentimento registra finalidade, versão da política e data/hora.

## Arquivos
| Arquivo | Papel |
|---|---|
| `web/index.html` | Página da jornada + `JORNADA_CONFIG` (único lugar a editar) |
| `web/formulario/formulario.html` | Formulário (fictício → oficial) |
| `web/assets/jornada/core.js` | Regras puras: etapas, acesso, estado, respostas, pontuação por pesos (testado com Node) |
| `web/assets/jornada/formulario.js` | Carrega o HTML, divide em telas, valida, lê e restaura respostas |
| `web/assets/jornada/adaptadores.js` | Integração com o servidor (pontuação, interesse, participação) |
| `web/assets/jornada/app.js` | Motor: rotas, progresso, telas, transições, foco |
| `web/assets/jornada/jornada.css` | Layout mobile first |
| `web/assets/graficos.js` | Gráficos compartilhados com `estatisticas.html` |
