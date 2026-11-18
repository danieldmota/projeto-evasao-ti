/* Motor da jornada guiada (index.html).
   - Rotas por hash (#/inicio ... #/fim): voltar/avançar do navegador funcionam.
   - Estado em sessionStorage, sem dados pessoais (ver core.js).
   - Cada etapa é um "renderer" que devolve { node, primary, back, onShow }. */

import {
  STEPS, FINAL, initialState, sanitizeState, resolveRoute, furthestAllowed, canContinue,
  prevStepId, stepIndex, stepStatus, progress, toSubmissionAnswers, scoreByWeights,
} from "./core.js";
import {
  loadForm, pagesOf, enhance, validatePage, readAnswers, multiNames, restoreAnswers,
  hasWeights, weightContributions,
} from "./formulario.js";
import { createAdapters, DISCLAIMER } from "./adaptadores.js";
import {
  SERIES, LABEL, pct, compact, nf, esc, legendHTML, renderLines, renderBars,
  annualTable, summaryTable, apiClient,
} from "../graficos.js";

// ------------------------------------------------------------------ configuração
const DEFAULTS = {
  api: "http://127.0.0.1:8000/api/v1",
  formulario: "formulario/formulario.html",
  conteudo: "conteudo/trilha-ti.json",
  pontuacao: "pesos",
  endpoints: { interesse: null, participacao: null },
  areas: SERIES.map(s => ({ code: s.code, label: s.label })),
  mapaAreasParaDados: {},
  projeto: {},
};
const userCfg = window.JORNADA_CONFIG || {};
const params = new URLSearchParams(location.search);
const cfg = {
  ...DEFAULTS, ...userCfg,
  api: (params.get("api") || userCfg.api || DEFAULTS.api).replace(/\/$/, ""),
  endpoints: { ...DEFAULTS.endpoints, ...(userCfg.endpoints || {}) },
  projeto: { ...DEFAULTS.projeto, ...(userCfg.projeto || {}) },
};
const adapters = createAdapters(cfg);
const api = apiClient(cfg.api);
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// ------------------------------------------------------------------ estado
const KEY = "evasao-ti:jornada";
let state = (() => {
  try { return sanitizeState(JSON.parse(sessionStorage.getItem(KEY))); } catch { return initialState(); }
})();
function save() {
  try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch { /* segue sem persistir */ }
}
function resetState() {
  state = initialState();
  formCache = null;
  try { sessionStorage.removeItem(KEY); } catch { /* ok */ }
}

// ------------------------------------------------------------------ DOM base
const $ = id => document.getElementById(id);
const stage = $("j-stage");
const btnBack = $("j-back");
const btnNext = $("j-next");
const hint = $("j-hint");
const announcer = $("j-announce");
let current = null;
let view = null;

function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}
const go = id => { location.hash = `#/${id}`; };
const top = () => window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
const topAreaFor = result => result?.affinities?.[0] || null;
const segmentFor = code => cfg.mapaAreasParaDados?.[code] ?? (LABEL[code] ? code : null);
const labelFor = code => cfg.areas.find(a => a.code === code)?.label || LABEL[code] || code;

// ------------------------------------------------------------------ cromo: trilha e progresso
function renderChrome(id) {
  const p = progress(id);
  const meta = STEPS[Math.min(p.index, STEPS.length - 1)];
  $("j-progress-label").textContent = id === FINAL
    ? "Jornada concluída"
    : `Etapa ${p.numero} de ${p.total} · ${meta.curto}`;
  $("j-progress-bar").innerHTML = STEPS.map(s => {
    const st = stepStatus(s.id, id, state);
    return `<span class="seg ${st}"></span>`;
  }).join("");
  $("j-steps").innerHTML = STEPS.map((s, i) => {
    const st = stepStatus(s.id, id, state);
    const clickable = st === "concluida" || st === "disponivel";
    const inner = `<span class="mark" aria-hidden="true">${st === "concluida" ? "✓" : i + 1}</span>
      <span class="txt"><span class="t">${esc(s.curto)}</span></span>`;
    const label = `${s.curto}${st === "concluida" ? " (concluída)" : st === "atual" ? " (etapa atual)" : st === "bloqueada" ? " (bloqueada)" : ""}`;
    return `<li class="${st}">${clickable
      ? `<a href="#/${s.id}" aria-label="${esc(label)}">${inner}</a>`
      : `<span ${st === "atual" ? 'aria-current="step"' : ""} aria-label="${esc(label)}">${inner}</span>`}</li>`;
  }).join("");
}

function setActions(v) {
  const prev = prevStepId(current);
  const showBack = v.back !== false && (typeof v.back === "function" || prev);
  btnBack.hidden = !showBack;
  hint.hidden = true;
  if (!v.primary) { btnNext.hidden = true; return; }
  btnNext.hidden = false;
  btnNext.textContent = v.primary.label;
  const blocked = v.primary.blocked?.() ?? false;
  btnNext.setAttribute("aria-disabled", String(blocked));
  btnNext.classList.toggle("is-blocked", blocked);
}
function refreshActions() { if (view) setActions(view); }

btnBack.addEventListener("click", () => {
  if (typeof view?.back === "function") return view.back();
  const prev = prevStepId(current);
  if (prev) go(prev);
});
btnNext.addEventListener("click", async () => {
  const p = view?.primary;
  if (!p || btnNext.classList.contains("is-loading")) return;
  if (p.blocked?.()) {
    hint.textContent = p.hint || "Complete esta etapa para continuar.";
    hint.hidden = false;
    p.onBlocked?.();
    return;
  }
  await p.onClick();
});

function setLoading(on, label) {
  btnNext.classList.toggle("is-loading", on);
  btnNext.setAttribute("aria-busy", String(on));
  if (label) btnNext.textContent = label;
}

// ------------------------------------------------------------------ roteador
async function route() {
  const requested = location.hash.replace(/^#\/?/, "") || "inicio";
  const target = resolveRoute(requested, state);
  if (target !== requested) {
    history.replaceState(null, "", `#/${target}`);
  }
  await show(target);
}

async function show(id) {
  const forward = current === null || stepIndex(id) >= stepIndex(current) || id === FINAL;
  view?.cleanup?.();          // remove listeners da etapa anterior (ex.: resize dos gráficos)
  current = id;
  view = await RENDER[id]();
  const node = view.node;
  node.classList.add("j-view");
  if (!reduceMotion) node.classList.add(forward ? "enter-fwd" : "enter-back");
  stage.replaceChildren(node);
  renderChrome(id);
  setActions(view);
  document.title = `${id === FINAL ? "Concluído" : STEPS[stepIndex(id)].titulo} · Permanência em TI`;
  const heading = node.querySelector("h1");
  if (heading) { heading.setAttribute("tabindex", "-1"); heading.focus({ preventScroll: true }); }
  announcer.textContent = $("j-progress-label").textContent;
  top();
  view.onShow?.();
}

window.addEventListener("hashchange", route);

// ------------------------------------------------------------------ conteúdo remoto (cache)
let contentPromise = null;
const loadContent = () => (contentPromise ??= fetch(cfg.conteudo).then(r => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}));
let statsPromise = null;
const loadStats = () => (statsPromise ??= Promise.all([
  api("/statistics/annual", { group_by: "segmento" }),
  api("/statistics/summary", { group_by: "segmento" }),
  api("/statistics/annual", { group_by: "total" }),
]).catch(e => { statsPromise = null; throw e; }));

let formCache = null;   // { form, pages } — mantém o que foi digitado entre telas

// ================================================================== etapas
const RENDER = {};

// ---------------------------------------------------------- 1. boas-vindas
RENDER.inicio = () => {
  const emAndamento = state.iniciado && !state.concluido;
  const node = h(`<section class="v-inicio">
    <p class="kicker">Orientação vocacional · leva poucos minutos</p>
    <h1 class="display">Descubra com o que você mais combina <em>e o que esperar da área de TI</em>.</h1>
    <p class="lead">Responda a algumas perguntas sobre seus interesses e veja na hora suas áreas de afinidade.
      Depois, conheça dados reais sobre o ensino superior e um caminho para começar a estudar.</p>
    <ol class="preview">
      <li><span class="n">1</span><div><strong>Responda</strong><span>Perguntas rápidas sobre o que você gosta de fazer.</span></div></li>
      <li><span class="n">2</span><div><strong>Descubra</strong><span>Suas áreas de maior afinidade, na hora.</span></div></li>
      <li><span class="n">3</span><div><strong>Planeje</strong><span>Dados de trancamento, competências e por onde começar.</span></div></li>
    </ol>
    <p class="fine">É uma ferramenta de orientação, não um teste psicológico. Suas respostas ficam só neste
      navegador e somem quando você fecha a aba.</p>
    ${emAndamento ? `<p class="resume">Você já começou. <button type="button" class="link" data-act="reset">Recomeçar do zero</button></p>` : ""}
  </section>`);
  node.querySelector('[data-act="reset"]')?.addEventListener("click", () => { resetState(); route(); });
  return {
    node,
    back: false,
    primary: {
      label: emAndamento ? "Continuar de onde parei" : "Começar",
      onClick: () => {
        if (!state.iniciado) {
          state.iniciado = true;
          state.session_id = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
          save();
        }
        go(emAndamento ? furthestAllowed(state) : "formulario");
      },
    },
  };
};

// ---------------------------------------------------------- 2. formulário
RENDER.formulario = async () => {
  const node = h(`<section class="v-form">
    <div class="form-head">
      <p class="kicker" id="q-counter">Carregando perguntas…</p>
      <div class="q-dots" id="q-dots" aria-hidden="true"></div>
    </div>
    <div class="form-host" id="form-host"><div class="skeleton" style="height:12rem"></div></div>
  </section>`);
  const host = node.querySelector("#form-host");
  const v = { node, primary: { label: "Próxima", onClick: async () => {} }, back: () => go("inicio") };

  try {
    if (!formCache) {
      const form = await loadForm(cfg.formulario);
      form.classList.add("jf-form");
      enhance(form);
      restoreAnswers(form, state.respostas);
      formCache = { form, pages: pagesOf(form) };
      const persist = () => { state.respostas = readAnswers(form); save(); };
      form.addEventListener("input", persist);
      form.addEventListener("change", persist);
      form.addEventListener("submit", e => { e.preventDefault(); btnNext.click(); });
    }
  } catch (err) {
    host.innerHTML = `<div class="error"><strong>O formulário não carregou.</strong> ${esc(err.message)}.
      <button type="button" class="link" data-act="retry">Tentar de novo</button></div>`;
    host.querySelector('[data-act="retry"]').addEventListener("click", () => route());
    v.primary = null;
    return v;
  }

  const { form, pages } = formCache;
  host.replaceChildren(form);
  const total = pages.length;
  state.paginaFormulario = Math.min(state.paginaFormulario, total - 1);

  const showPage = (dir = 0) => {
    const i = state.paginaFormulario;
    pages.forEach((p, k) => {
      p.hidden = pages.length > 1 && k !== i;
      p.classList.remove("enter-fwd", "enter-back");
    });
    if (dir && !reduceMotion) pages[i].classList.add(dir > 0 ? "enter-fwd" : "enter-back");
    node.querySelector("#q-counter").textContent = total > 1 ? `Pergunta ${i + 1} de ${total}` : "Suas respostas";
    node.querySelector("#q-dots").innerHTML = pages.map((_, k) =>
      `<span class="${k < i ? "done" : k === i ? "now" : ""}"></span>`).join("");
    v.primary.label = i === total - 1 ? "Ver meu resultado" : "Próxima pergunta";
    refreshActions();
    if (dir) {
      const legend = pages[i].querySelector("legend");
      if (legend) { legend.setAttribute("tabindex", "-1"); legend.focus({ preventScroll: true }); }
      announcer.textContent = node.querySelector("#q-counter").textContent;
      top();
    }
  };

  v.back = () => {
    if (state.paginaFormulario > 0) { state.paginaFormulario--; save(); showPage(-1); }
    else go("inicio");
  };
  v.primary.onClick = async () => {
    const page = pages[state.paginaFormulario];
    const check = validatePage(page);
    if (!check.ok) { check.first?.focus(); return; }
    if (state.paginaFormulario < total - 1) {
      state.paginaFormulario++; save(); showPage(1); return;
    }
    setLoading(true, "Calculando…");
    try {
      state.respostas = readAnswers(form);
      const submission = {
        session_id: state.session_id,
        questionnaire_id: form.dataset.questionnaireId || "sem-id",
        questionnaire_version: form.dataset.questionnaireVersion || "sem-versao",
        answers: toSubmissionAnswers(state.respostas, multiNames(form)),
        locale: "pt-BR",
      };
      const local = () => hasWeights(form) ? scoreByWeights(weightContributions(form), cfg.areas) : null;
      state.resultado = await adapters.pontuar(submission, local);
      state.formularioConcluido = true;
      save();
      go("resultado");
    } catch (err) {
      const errBox = page.querySelector(".jf-error");
      if (errBox) { errBox.hidden = false; errBox.textContent = `Não foi possível calcular o resultado: ${err.message}`; }
    } finally {
      setLoading(false);
      refreshActions();
    }
  };
  v.onShow = () => showPage(0);
  return v;
};

// ---------------------------------------------------------- 3. resultado
RENDER.resultado = () => {
  const r = state.resultado;
  const lead = topAreaFor(r);
  const node = h(`<section class="v-resultado">
    ${r.demonstracao ? `<p class="note demo"><span class="kicker">Demonstração</span>
      Resultado calculado com os pesos do formulário fictício. Não é o algoritmo oficial.</p>` : ""}
    <p class="kicker">Seu resultado</p>
    <h1 class="display">Sua maior afinidade é com <em>${esc(lead?.area_label || labelFor(lead?.area_code))}</em>.</h1>
    <ol class="affinities" aria-label="Áreas em ordem de afinidade"></ol>
    <p class="fine">Pontuação relativa: a área com mais afinidade vale 100. ${esc(r.disclaimer || DISCLAIMER)}</p>
    <p><button type="button" class="link" data-act="redo">Refazer o formulário</button></p>
  </section>`);
  node.querySelector(".affinities").innerHTML = r.affinities.map((a, i) => {
    const seg = segmentFor(a.area_code);
    const score = Math.round(a.score * 100);
    return `<li style="--i:${i}">
      <span class="rank">${a.rank}º</span>
      <span class="name">${esc(a.area_label || labelFor(a.area_code))}</span>
      <span class="track"><span class="fill" style="--w:${a.score};${seg ? `--c:var(--s-${seg})` : ""}"></span></span>
      <span class="val">${score}</span>
    </li>`;
  }).join("");
  node.querySelector('[data-act="redo"]').addEventListener("click", () => {
    state.resultado = null; state.formularioConcluido = false; state.paginaFormulario = 0;
    save(); go("formulario");
  });
  return {
    node,
    back: () => go("formulario"),
    primary: { label: "Continuar", onClick: () => go("interesse") },
    onShow: () => requestAnimationFrame(() => node.classList.add("is-ready")),
  };
};

// ---------------------------------------------------------- 4. interesse em TI
RENDER.interesse = () => {
  const lead = topAreaFor(state.resultado);
  const leadIsTI = segmentFor(lead?.area_code) === "TI";
  const node = h(`<section class="v-interesse">
    <p class="kicker">Uma pergunta rápida</p>
    <h1 class="display">Você tem interesse em cursar uma graduação na área de TI?</h1>
    <p class="lead">${leadIsTI
      ? "Seu resultado aponta afinidade com Tecnologia da Informação."
      : `Seu resultado aponta mais afinidade com ${esc(lead?.area_label || labelFor(lead?.area_code))}. Tudo bem: muita gente chega à TI por outros caminhos.`}</p>
    <fieldset class="choices">
      <legend class="visually-hidden">Interesse em cursar TI</legend>
      <label class="choice"><input type="radio" name="interesse" value="sim">
        <span class="c-title">Sim, quero cursar TI</span><span class="c-sub">Já é um plano ou uma vontade forte.</span></label>
      <label class="choice"><input type="radio" name="interesse" value="talvez">
        <span class="c-title">Talvez, ainda estou decidindo</span><span class="c-sub">Quero conhecer melhor antes de escolher.</span></label>
      <label class="choice"><input type="radio" name="interesse" value="nao">
        <span class="c-title">Não, meu interesse é outra área</span><span class="c-sub">Mesmo assim, você pode seguir e conhecer os dados.</span></label>
    </fieldset>
  </section>`);
  const radios = node.querySelectorAll('input[name="interesse"]');
  radios.forEach(r => {
    r.checked = r.value === state.interesse;
    r.addEventListener("change", () => {
      state.interesse = r.value; save(); refreshActions();
      adapters.registrarInteresse({ session_id: state.session_id, interest: r.value }).catch(() => {});
    });
  });
  return {
    node,
    primary: {
      label: "Continuar",
      blocked: () => !canContinue("interesse", state),
      hint: "Escolha uma das opções para continuar.",
      onBlocked: () => radios[0].focus(),
      onClick: () => go("projeto"),
    },
  };
};

// ---------------------------------------------------------- 5. convite ao projeto
RENDER.projeto = () => {
  const P = cfg.projeto;
  const titulo = state.interesse === "nao"
    ? "Você pode ajudar estudantes de TI a seguir no curso."
    : "Quer participar de um projeto para ajudar estudantes de TI a seguir no curso?";
  const node = h(`<section class="v-projeto">
    <p class="kicker">Convite</p>
    <h1 class="display">${esc(titulo)}</h1>
    <p class="lead">${esc(P.descricao || "")}</p>
    <div class="projeto-grid">
      <form class="pform" novalidate>
        <label class="field">Seu nome
          <input name="nome" autocomplete="name" required maxlength="120"></label>
        <label class="field">Seu e-mail
          <input name="email" type="email" autocomplete="email" inputmode="email" required maxlength="254"></label>
        <label class="consent"><input type="checkbox" name="consentimento" required>
          <span>Concordo que meu nome e e-mail sejam usados <strong>apenas</strong> para contato sobre este projeto,
          conforme a <a href="${esc(P.politicaUrl || "#")}" target="_blank" rel="noopener">política de privacidade</a>${P.politicaUrl && P.politicaUrl !== "#" ? "" : " (em elaboração)"}.</span></label>
        <p class="jf-error" role="alert" hidden></p>
        <div class="pform-actions">
          <button type="submit" class="btn primary">Quero participar</button>
          <button type="button" class="btn ghost" data-act="skip">Agora não</button>
        </div>
      </form>
      <aside class="lgpd" aria-label="Como seus dados são tratados">
        <h2>Seus dados, com transparência</h2>
        <dl>
          <dt>O que coletamos</dt><dd>Só nome e e-mail. As respostas do formulário não ficam ligadas a você.</dd>
          <dt>Para quê</dt><dd>${esc(P.finalidade || "")}</dd>
          <dt>Por quanto tempo</dt><dd>${esc(P.retencao || "")}</dd>
          <dt>Seus direitos</dt><dd>Você pode pedir acesso, correção ou exclusão dos seus dados e retirar o consentimento quando quiser.</dd>
        </dl>
      </aside>
    </div>
    <div class="done-box" hidden></div>
  </section>`);
  const form = node.querySelector(".pform");
  const err = form.querySelector(".jf-error");
  const doneBox = node.querySelector(".done-box");

  const showDone = status => {
    const msg = {
      enviada: ["Inscrição enviada.", "A equipe do projeto vai entrar em contato pelo e-mail informado."],
      demonstracao: ["Modo demonstração: nada foi enviado.",
        "Seus dados não foram enviados nem guardados. O envio será ativado quando o servidor do projeto estiver pronto."],
      recusada: ["Tudo bem!", "Você pode continuar a jornada normalmente."],
    }[status];
    node.querySelector(".projeto-grid").hidden = true;
    doneBox.hidden = false;
    doneBox.className = `done-box ${status}`;
    doneBox.innerHTML = `<p class="done-title">${esc(msg[0])}</p><p>${esc(msg[1])}</p>
      <button type="button" class="link" data-act="change">Mudar minha resposta</button>`;
    doneBox.querySelector('[data-act="change"]').addEventListener("click", () => {
      state.participacao = null; save(); route();
    });
  };
  if (state.participacao) showDone(state.participacao);

  form.addEventListener("submit", async e => {
    e.preventDefault();
    const nome = form.nome.value.trim(), email = form.email.value.trim();
    const problems = [];
    if (!nome) problems.push([form.nome, "Informe seu nome."]);
    if (!form.email.checkValidity() || !email) problems.push([form.email, "Informe um e-mail válido."]);
    if (!form.consentimento.checked) problems.push([form.consentimento, "Para participar, é preciso concordar com o uso dos dados."]);
    form.querySelectorAll("[aria-invalid]").forEach(x => x.removeAttribute("aria-invalid"));
    if (problems.length) {
      problems.forEach(([f]) => f.setAttribute("aria-invalid", "true"));
      err.hidden = false; err.textContent = problems[0][1]; problems[0][0].focus();
      return;
    }
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true; submit.textContent = "Enviando…";
    try {
      const res = await adapters.participar({
        session_id: null,     // minimização: não liga a inscrição às respostas do teste
        name: nome, email,
        consent: {
          granted: true,
          purpose_code: P.purposeCode,
          privacy_policy_version: P.politicaVersao,
          granted_at: new Date().toISOString(),
        },
      });
      form.reset();           // dados pessoais saem da tela e nunca vão para o armazenamento
      state.participacao = res.status; save();
      showDone(res.status); refreshActions();
    } catch (ex) {
      err.hidden = false; err.textContent = `Não foi possível enviar agora: ${ex.message}. Tente de novo.`;
    } finally {
      submit.disabled = false; submit.textContent = "Quero participar";
    }
  });
  form.querySelector('[data-act="skip"]').addEventListener("click", () => {
    form.reset();
    state.participacao = "recusada"; save(); go("dados");
  });

  return {
    node,
    primary: {
      label: "Continuar",
      blocked: () => !canContinue("projeto", state),
      hint: "Escolha \"Quero participar\" ou \"Agora não\" para continuar.",
      onBlocked: () => form.nome.focus(),
      onClick: () => go("dados"),
    },
  };
};

// ---------------------------------------------------------- 6. dados
RENDER.dados = () => {
  const lead = topAreaFor(state.resultado);
  const seg = segmentFor(lead?.area_code);
  const hl = seg && seg !== "TI" ? seg : null;
  const node = h(`<section class="v-dados">
    <p class="kicker">O que dizem os dados · Censo da Educação Superior (INEP)</p>
    <h1 class="display" id="d-head">Trancamento no ensino superior</h1>
    <p class="lead" id="d-dek"><span class="skeleton-line"></span></p>
    <figure class="fig">
      <figcaption><span class="kicker">Figura 1</span><h2>Taxa de trancamento por área, ano a ano</h2>
        <p>${hl ? `Em destaque: TI e sua área de maior afinidade (${esc(LABEL[hl])}).` : "TI em destaque."} Toque ou passe o mouse para ver cada ano.</p></figcaption>
      <ul class="legend">${legendHTML()}</ul>
      <div class="chart" id="d-lines"><div class="skeleton" style="height:16rem"></div></div>
      <details><summary>Ver os dados em tabela</summary><div class="table-wrap" id="d-t1"></div></details>
    </figure>
    <figure class="fig">
      <figcaption><span class="kicker">Figura 2</span><h2>Consolidado do período</h2>
        <p>Soma de todos os anos (vínculos-ano, não pessoas).</p></figcaption>
      <div class="chart" id="d-bars"></div>
      <details><summary>Ver os dados em tabela</summary><div class="table-wrap" id="d-t2"></div></details>
    </figure>
    <p class="source">Fonte: INEP, microdados do Censo da Educação Superior. Cálculo próprio; não é estatística oficial.
      <a href="estatisticas.html">Explorar com filtros</a>.</p>
    <p class="note"><span class="kicker">Importante</span> Trancar não é o mesmo que desistir. Muitas vezes, é um sinal de
      que algo precisa de apoio. Nas próximas etapas, veja o que ajuda a seguir no curso.</p>
  </section>`);
  let data = null;
  const draw = () => {
    if (!data) return;
    const [annual, summary] = data;
    const years = annual.meta.periodo.anos_com_dados;
    renderLines(node.querySelector("#d-lines"), annual.data, years,
      { highlight: hl, highlightLabel: hl ? "Sua área" : undefined });
    node.querySelector("#d-t1").innerHTML = annualTable(annual.data, years);
    renderBars(node.querySelector("#d-bars"), summary.data, { highlight: hl });
    node.querySelector("#d-t2").innerHTML = summaryTable(summary.data);
  };
  const onResize = debounce(draw, 150);
  return {
    node,
    primary: { label: "Continuar", onClick: () => go("competencias") },
    onShow: async () => {
      window.addEventListener("resize", onResize);
      try {
        data = await loadStats();
        const [annual, , total] = data;
        const years = annual.meta.periodo.anos_com_dados;
        const last = years[years.length - 1];
        const ti = annual.data.find(r => r.ano === last && r.grupo_codigo === "TI");
        const all = total.data.find(r => r.ano === last);
        const cmp = all?.taxa_trancamento == null ? "" :
          `, ${ti.taxa_trancamento > all.taxa_trancamento ? "acima" : "abaixo"} da média de todas as áreas (${pct(all.taxa_trancamento)})`;
        node.querySelector("#d-head").innerHTML =
          `Em ${last}, <em class="num">${pct(ti.taxa_trancamento)}</em> dos vínculos em cursos de TI estavam trancados${cmp}.`;
        node.querySelector("#d-dek").innerHTML =
          `São <strong>${compact(ti.trancadas)}</strong> matrículas trancadas em <strong>${nf.format(ti.matriculas + ti.trancadas)}</strong> vínculos de TI no ano.`;
        node.querySelector("#d-lines").replaceChildren();
        draw();
      } catch (e) {
        node.querySelector("#d-dek").textContent = "";
        node.querySelector("#d-lines").innerHTML = `<div class="error"><strong>Os dados não carregaram.</strong>
          Verifique se a API está rodando (<code>evasao-ti serve</code>). Você pode continuar a jornada mesmo assim.</div>`;
      }
    },
    cleanup: () => window.removeEventListener("resize", onResize),
  };
};

// ---------------------------------------------------------- 7. competências
RENDER.competencias = () => {
  const node = h(`<section class="v-comp">
    <p class="kicker">Competências</p>
    <h1 class="display">Cinco competências que você vai desenvolver em TI</h1>
    <p class="lead" id="c-intro"><span class="skeleton-line"></span></p>
    <div class="acc" id="c-list"><div class="skeleton" style="height:14rem"></div></div>
  </section>`);
  return {
    node,
    primary: { label: "Continuar", onClick: () => go("estudos") },
    onShow: async () => {
      try {
        const c = await loadContent();
        const R = c.recursos;
        node.querySelector("#c-intro").textContent = c.competencias.introducao;
        node.querySelector("#c-list").innerHTML = c.competencias.itens.map((it, i) => `
          <details class="acc-item" ${i === 0 ? "open" : ""} style="--i:${i}">
            <summary><span class="numeral">${i + 1}</span>
              <span class="acc-title"><span class="t">${esc(it.titulo)}</span><span class="s">${esc(it.resumo)}</span></span>
              <span class="chev" aria-hidden="true"></span></summary>
            <div class="acc-body">
              <div><span class="kicker">Por que importa</span><p>${esc(it.por_que_importa)}</p></div>
              <div><span class="kicker">Como desenvolver</span><ul>${it.como_desenvolver.map(t => `<li>${esc(t)}</li>`).join("")}</ul></div>
              <p class="practice">Para praticar: ${it.recursos.filter(id => R[id]).map(id =>
                `<a href="${esc(safeUrl(R[id].url))}" target="_blank" rel="noopener noreferrer">${esc(R[id].nome)}<span class="visually-hidden"> (abre em nova aba)</span></a>`).join(" · ")}</p>
            </div>
          </details>`).join("");
      } catch (e) {
        node.querySelector("#c-list").innerHTML = `<div class="error">O conteúdo não carregou (${esc(e.message)}).</div>`;
      }
    },
  };
};

// ---------------------------------------------------------- 8. estudos
RENDER.estudos = () => {
  const intro = {
    sim: "Um caminho para começar antes mesmo da faculdade.",
    talvez: "Experimente as primeiras etapas: elas ajudam a descobrir se TI é para você.",
    nao: "Se um dia mudar de ideia, este é um bom ponto de partida.",
  }[state.interesse] || "";
  const node = h(`<section class="v-estudos">
    <p class="kicker">Por onde começar</p>
    <h1 class="display">Sua trilha de estudos para começar em TI</h1>
    <p class="lead">${esc(intro)} Todos os materiais são gratuitos.</p>
    <ol class="timeline" id="e-steps"><li><div class="skeleton" style="height:12rem"></div></li></ol>
    <div class="habits-wrap" id="e-habits"></div>
    <aside class="band" id="e-band" hidden></aside>
  </section>`);
  return {
    node,
    primary: { label: "Concluir jornada", onClick: () => { state.concluido = true; save(); go(FINAL); } },
    onShow: async () => {
      try {
        const c = await loadContent();
        const R = c.recursos, rec = c.recomendacoes;
        node.querySelector("#e-steps").innerHTML = rec.etapas.map((e, i) => {
          const res = e.recursos.filter(id => R[id]).map(id => R[id]);
          const item = r => `<li><a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">
              <span class="name">${esc(r.nome)}</span><span class="visually-hidden"> (abre em nova aba)</span>
              <span class="meta">${esc(r.idioma)} · ${esc(r.custo)}</span></a></li>`;
          return `<li class="step">
            <span class="dot" aria-hidden="true">${i + 1}</span>
            <h2>${esc(e.titulo.replace(/^\d+\.\s*/, ""))}</h2>
            <p class="when kicker">${esc(e.quando)}</p>
            <ul class="obj">${e.objetivos.map(t => `<li>${esc(t)}</li>`).join("")}</ul>
            <ul class="res">${res.slice(0, 2).map(item).join("")}</ul>
            ${res.length > 2 ? `<details class="more"><summary>Mais ${res.length - 2} ${res.length - 2 === 1 ? "material" : "materiais"}</summary>
              <ul class="res">${res.slice(2).map(item).join("")}</ul></details>` : ""}
          </li>`;
        }).join("");
        node.querySelector("#e-habits").innerHTML = `<h2>${esc(rec.habitos.titulo)}</h2>
          <ul class="habits">${rec.habitos.itens.map(t => `<li>${esc(t)}</li>`).join("")}</ul>`;
        const band = node.querySelector("#e-band");
        band.hidden = false;
        band.innerHTML = `<span class="kicker">Antes de decidir</span><h2>${esc(rec.antes_de_trancar.titulo)}</h2>
          <p>${esc(rec.antes_de_trancar.texto)}</p>
          <ul>${rec.antes_de_trancar.itens.map(t => `<li>${esc(t)}</li>`).join("")}</ul>`;
      } catch (e) {
        node.querySelector("#e-steps").innerHTML = `<li><div class="error">O conteúdo não carregou (${esc(e.message)}).</div></li>`;
      }
    },
  };
};

// ---------------------------------------------------------- fim
RENDER[FINAL] = () => {
  const lead = topAreaFor(state.resultado);
  const interesse = { sim: "Sim, quero cursar TI", talvez: "Talvez, ainda estou decidindo", nao: "Meu interesse é outra área" }[state.interesse];
  const part = { enviada: "Inscrição enviada", demonstracao: "Demonstração (nada foi enviado)", recusada: "Preferiu não participar agora" }[state.participacao];
  const node = h(`<section class="v-fim">
    <p class="kicker">Jornada concluída</p>
    <h1 class="display">Bom começo! <em>O próximo passo é seu.</em></h1>
    <dl class="recap">
      <div><dt>Maior afinidade</dt><dd>${esc(lead?.area_label || labelFor(lead?.area_code) || "—")}${state.resultado?.demonstracao ? " <small>(demonstração)</small>" : ""}</dd></div>
      <div><dt>Interesse em TI</dt><dd>${esc(interesse || "—")}</dd></div>
      <div><dt>Projeto de permanência</dt><dd>${esc(part || "—")}</dd></div>
    </dl>
    <div class="next-links">
      <a class="card-link" href="#/resultado"><span class="t">Rever meu resultado</span><span class="s">Suas áreas de afinidade</span></a>
      <a class="card-link" href="#/dados"><span class="t">Rever os dados</span><span class="s">Trancamento por área</span></a>
      <a class="card-link" href="#/estudos"><span class="t">Minha trilha de estudos</span><span class="s">Materiais gratuitos</span></a>
    </div>
    <p class="fine">Suas respostas estão só neste navegador e somem ao fechar a aba.
      <button type="button" class="link" data-act="wipe">Apagar agora e recomeçar</button></p>
  </section>`);
  node.querySelector('[data-act="wipe"]').addEventListener("click", () => { resetState(); go("inicio"); });
  return {
    node,
    back: () => go("estudos"),
    primary: null,
  };
};

// ------------------------------------------------------------------ utilidades
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
function safeUrl(u) { return /^https:\/\//.test(u) ? u : "#"; }

route();
