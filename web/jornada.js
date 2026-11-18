// Jornada guiada (index.html): rotas por hash (#/inicio ... #/fim), estado na sessionStorage
// (sem nenhum dado pessoal) e uma função de desenho para cada etapa.
import {
  AREAS, NOME_AREA, pct, compacto, nf, esc, legendaHTML,
  graficoLinhas, graficoBarras, tabelaAnual, tabelaResumo, criarApi,
} from "./graficos.js";

// configuração
const conf = window.JORNADA_CONFIG || {};
const cfg = {
  formulario: "formulario.html",
  conteudo: "trilha.json",
  pontuacao: "pesos",
  mapaAreasParaDados: {},
  ...conf,
  endpoints: conf.endpoints || {},
  projeto: conf.projeto || {},
  api: (new URLSearchParams(location.search).get("api") || conf.api || "/api/v1").replace(/\/$/, ""),
};
const api = criarApi(cfg.api);
const semMovimento = matchMedia("(prefers-reduced-motion: reduce)").matches;
const AVISO = "Este resultado é uma ferramenta de orientação para reflexão sobre interesses. " +
  "Não é um diagnóstico psicológico nem um teste validado.";

const ETAPAS = [
  { id: "inicio", titulo: "Boas-vindas", curto: "Início" },
  { id: "formulario", titulo: "Seus interesses", curto: "Formulário" },
  { id: "resultado", titulo: "Suas áreas de afinidade", curto: "Resultado" },
  { id: "interesse", titulo: "Interesse em TI", curto: "Interesse em TI" },
  { id: "projeto", titulo: "Projeto de permanência", curto: "Projeto" },
  { id: "dados", titulo: "O que dizem os dados", curto: "Dados" },
  { id: "competencias", titulo: "Competências em TI", curto: "Competências" },
  { id: "estudos", titulo: "Por onde começar", curto: "Estudos" },
];
const IDS = ETAPAS.map(e => e.id);

// estado
const CHAVE = "evasao-ti:jornada";
const novoEstado = () => ({
  versao: 2, sessao: null, iniciado: false, respostas: {}, pagina: 0,
  resultado: null, interesse: null, concluido: false,
});
let estado = (() => {
  try {
    const s = JSON.parse(sessionStorage.getItem(CHAVE));
    if (!s || s.versao !== 2) return novoEstado();
    if (!Array.isArray(s.resultado?.affinities)) s.resultado = null;
    if (!["sim", "talvez", "nao"].includes(s.interesse)) s.interesse = null;
    return { ...novoEstado(), ...s };
  } catch { return novoEstado(); }
})();
function salvar() {
  try { sessionStorage.setItem(CHAVE, JSON.stringify(estado)); } catch { /* segue sem salvar */ }
}
function recomecar() {
  estado = novoEstado();
  formulario = null;
  try { sessionStorage.removeItem(CHAVE); } catch { /* ok */ }
}

// o que precisa estar feito para entrar em cada etapa
const REQUISITO = {
  inicio: () => true,
  formulario: () => estado.iniciado,
  resultado: () => !!estado.resultado,
  interesse: () => !!estado.resultado,
  projeto: () => !!estado.interesse,
  dados: () => !!estado.interesse,
  competencias: () => !!estado.interesse,
  estudos: () => !!estado.interesse,
  fim: () => estado.concluido,
};
const pode = id => REQUISITO[id]?.() ?? false;
function maisAvancada() {
  if (pode("fim")) return "fim";
  let ultima = "inicio";
  for (const id of IDS) { if (!pode(id)) break; ultima = id; }
  return ultima;
}

// elementos e utilidades
const $ = id => document.getElementById(id);
const palco = $("j-stage"), btVoltar = $("j-back"), btAvancar = $("j-next"), dica = $("j-hint"), aviso = $("j-announce");
let atual = null;
let tela = null;

function html(texto) {
  const t = document.createElement("template");
  t.innerHTML = texto.trim();
  return t.content.firstElementChild;
}
const ir = id => { location.hash = `#/${id}`; };
const subir = () => window.scrollTo({ top: 0, behavior: semMovimento ? "auto" : "smooth" });
const urlSegura = u => /^https:\/\//.test(u || "") ? u : "#";
const lider = () => estado.resultado?.affinities?.[0] || null;
const areaDados = codigo => cfg.mapaAreasParaDados[codigo] ?? (NOME_AREA[codigo] ? codigo : null);
const nomeArea = a => a?.area_label || NOME_AREA[a?.area_code] || a?.area_code || "—";
const dataBR = iso => iso ? iso.split("-").reverse().join("/") : "";
function adiar(fn, ms) { let t; return () => { clearTimeout(t); t = setTimeout(fn, ms); }; }

async function postar(url, corpo) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(corpo),
  });
  const dados = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(dados?.error?.message || `HTTP ${resp.status}`);
  return dados;
}

// progresso e botões
function situacao(id) {
  if (id === atual) return "atual";
  const passou = atual === "fim" || IDS.indexOf(id) < IDS.indexOf(atual);
  if (!pode(id)) return "bloqueada";
  return passou ? "concluida" : "disponivel";
}

function desenharProgresso() {
  const i = atual === "fim" ? ETAPAS.length : IDS.indexOf(atual);
  $("j-progress-label").textContent = atual === "fim"
    ? "Jornada concluída" : `Etapa ${i + 1} de ${ETAPAS.length} · ${ETAPAS[i].curto}`;
  $("j-progress-bar").innerHTML = ETAPAS.map(e => `<span class="${situacao(e.id)}"></span>`).join("");
  $("j-steps").innerHTML = ETAPAS.map((e, n) => {
    const s = situacao(e.id);
    const extra = { concluida: " (concluída)", atual: " (etapa atual)", bloqueada: " (bloqueada)" }[s] || "";
    const dentro = `<span class="mark" aria-hidden="true">${s === "concluida" ? "✓" : n + 1}</span><span class="t">${esc(e.curto)}</span>`;
    return `<li class="${s}">${s === "concluida" || s === "disponivel"
      ? `<a href="#/${e.id}" aria-label="${esc(e.curto + extra)}">${dentro}</a>`
      : `<span ${s === "atual" ? 'aria-current="step"' : ""} aria-label="${esc(e.curto + extra)}">${dentro}</span>`}</li>`;
  }).join("");
}

function atualizarBotoes() {
  btVoltar.hidden = tela.voltar === false || (!tela.voltar && atual === "inicio");
  dica.hidden = true;
  const p = tela.principal;
  btAvancar.hidden = !p;
  if (!p) return;
  btAvancar.textContent = p.texto;
  const bloqueado = p.bloqueado?.() ?? false;
  btAvancar.setAttribute("aria-disabled", String(bloqueado));
  btAvancar.classList.toggle("bloqueado", bloqueado);
}

function carregando(sim, texto) {
  btAvancar.classList.toggle("carregando", sim);
  btAvancar.setAttribute("aria-busy", String(sim));
  if (texto) btAvancar.textContent = texto;
}

// o link "pular para o conteúdo" não pode mexer no hash (o hash é a rota)
document.querySelector(".skip").addEventListener("click", e => { e.preventDefault(); $("conteudo").focus(); });

btVoltar.addEventListener("click", () => {
  if (typeof tela?.voltar === "function") return tela.voltar();
  ir(atual === "fim" ? "estudos" : IDS[IDS.indexOf(atual) - 1]);
});
btAvancar.addEventListener("click", async () => {
  const p = tela?.principal;
  if (!p || btAvancar.classList.contains("carregando")) return;
  if (p.bloqueado?.()) {
    dica.textContent = p.dica;
    dica.hidden = false;
    p.aoBloquear?.();
    return;
  }
  await p.acao();
});

// rotas
async function rota() {
  const pedida = location.hash.replace(/^#\/?/, "") || "inicio";
  const destino = Object.hasOwn(REQUISITO, pedida) && pode(pedida) ? pedida : maisAvancada();
  if (destino !== pedida) history.replaceState(null, "", `#/${destino}`);
  await mostrar(destino);
}

async function mostrar(id) {
  const frente = atual === null || id === "fim" || IDS.indexOf(id) >= IDS.indexOf(atual);
  tela?.limpar?.();
  atual = id;
  tela = await ETAPA[id]();
  const no = tela.no;
  no.classList.add("j-view");
  if (!semMovimento) no.classList.add(frente ? "entra-frente" : "entra-tras");
  palco.replaceChildren(no);
  desenharProgresso();
  atualizarBotoes();
  document.title = `${id === "fim" ? "Concluído" : ETAPAS[IDS.indexOf(id)].titulo} · Permanência em TI`;
  const h1 = no.querySelector("h1");
  if (h1) { h1.tabIndex = -1; h1.focus({ preventScroll: true }); }
  aviso.textContent = $("j-progress-label").textContent;
  subir();
  tela.aoMostrar?.();
}

window.addEventListener("hashchange", rota);

// dados carregados uma vez só
let conteudo = null;
const carregarConteudo = () => (conteudo ??= fetch(cfg.conteudo).then(r => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}).catch(e => { conteudo = null; throw e; }));

let estatisticas = null;
const carregarEstatisticas = () => (estatisticas ??= Promise.all([
  api("/statistics/annual", { group_by: "segmento" }),
  api("/statistics/summary", { group_by: "segmento" }),
  api("/statistics/annual", { group_by: "total" }),
]).catch(e => { estatisticas = null; throw e; }));

// formulário vocacional
let formulario = null; // { form, paginas } fica em memória para não perder o que foi digitado

const camposDe = raiz => [...raiz.querySelectorAll("input, select, textarea")]
  .filter(c => c.name && !c.disabled && c.type !== "submit" && c.type !== "button");

async function carregarFormulario() {
  const resp = await fetch(cfg.formulario, { cache: "no-cache" });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const doc = new DOMParser().parseFromString(await resp.text(), "text/html");
  const form = doc.querySelector("form");
  if (!form) throw new Error("o arquivo não tem um <form>");
  form.querySelectorAll("script").forEach(s => s.remove());
  form.querySelectorAll("*").forEach(n => [...n.attributes].forEach(a => /^on/i.test(a.name) && n.removeAttribute(a.name)));
  form.classList.add("jf-form");
  form.noValidate = true;

  const paginas = [...form.querySelectorAll(":scope > fieldset")];
  if (!paginas.length) paginas.push(form);
  paginas.forEach((pag, i) => {
    // mensagem de erro logo abaixo da pergunta
    const erro = html(`<p class="jf-erro" id="jf-erro-${i}" role="alert" hidden></p>`);
    const ancora = pag.querySelector(":scope > .ajuda") || pag.querySelector(":scope > legend");
    ancora ? ancora.after(erro) : pag.prepend(erro);
    camposDe(pag).forEach(c => c.setAttribute("aria-describedby", erro.id));
  });
  form.querySelectorAll('input[type="range"]').forEach(r => {
    const min = r.dataset.rotuloMin, max = r.dataset.rotuloMax;
    const caixa = html(`<div class="jf-escala"><output></output><div class="jf-pontas"><span>${esc(min || r.min)}</span><span>${esc(max || r.max)}</span></div></div>`);
    r.replaceWith(caixa);
    caixa.querySelector("output").after(r);
    if (!r.getAttribute("aria-label")) r.setAttribute("aria-label", r.closest("fieldset")?.querySelector("legend")?.textContent.trim() || r.name);
    const sync = () => {
      caixa.querySelector("output").textContent = r.value;
      r.style.setProperty("--t", (r.value - r.min) / ((r.max - r.min) || 1));
      r.setAttribute("aria-valuetext", r.value + (min && max ? ` (de ${min} a ${max})` : ""));
    };
    r.addEventListener("input", sync);
    sync();
  });

  // restaura respostas salvas
  for (const c of camposDe(form)) {
    if (!(c.name in estado.respostas)) continue;
    const v = [].concat(estado.respostas[c.name]).map(String);
    if (c.type === "radio" || c.type === "checkbox") c.checked = v.includes(c.value);
    else if (c.multiple) [...c.options].forEach(o => { o.selected = v.includes(o.value); });
    else c.value = v[0];
    c.dispatchEvent(new Event("input"));
  }
  const guardar = () => { estado.respostas = lerRespostas(form); salvar(); };
  form.addEventListener("input", guardar);
  form.addEventListener("change", guardar);
  form.addEventListener("submit", e => { e.preventDefault(); btAvancar.click(); });
  return { form, paginas };
}

function lerRespostas(form) {
  const numericos = new Set(camposDe(form).filter(c => c.type === "range" || c.type === "number").map(c => c.name));
  const r = {};
  for (const [nome, valor] of new FormData(form)) {
    if (typeof valor !== "string") continue;
    const v = numericos.has(nome) && valor !== "" ? Number(valor) : valor;
    r[nome] = nome in r ? [].concat(r[nome], v) : v;
  }
  return r;
}

function validar(pag) {
  let msg = "", primeiro = null;
  for (const c of camposDe(pag)) {
    if (c.checkValidity()) continue;
    primeiro = c;
    msg = c.dataset.erro || (c.validity.valueMissing
      ? (c.type === "radio" ? "Escolha uma opção para continuar." : "Preencha este campo para continuar.")
      : c.validity.tooLong ? `Use no máximo ${c.maxLength} caracteres.` : c.validationMessage);
    break;
  }
  const caixas = pag.querySelectorAll('input[type="checkbox"]');
  if (!msg && caixas.length) {
    const marcadas = pag.querySelectorAll('input[type="checkbox"]:checked').length;
    const min = Number(pag.dataset.min || 0), max = Number(pag.dataset.max || Infinity);
    if (marcadas < min) msg = min === 1 ? "Marque pelo menos uma opção." : `Marque pelo menos ${min} opções.`;
    else if (marcadas > max) msg = `Marque no máximo ${max} opções.`;
    if (msg) primeiro = caixas[0];
  }
  const erro = pag.querySelector(".jf-erro");
  erro.textContent = msg;
  erro.hidden = !msg;
  camposDe(pag).forEach(c => c.toggleAttribute("aria-invalid", c === primeiro));
  return primeiro;
}

// "TI:2, EXATAS_EXCETO_TI:1" -> { TI: 2, EXATAS_EXCETO_TI: 1 }
function lerPesos(texto) {
  const pesos = {};
  for (const parte of (texto || "").split(",")) {
    const [area, n] = parte.split(":").map(s => s?.trim());
    if (area && Number.isFinite(Number(n))) pesos[area] = (pesos[area] || 0) + Number(n);
  }
  return pesos;
}

// pontuação de demonstração: soma os data-pesos marcados e divide pela área líder
function pontuarPorPesos(form) {
  const total = Object.fromEntries(AREAS.map(a => [a.codigo, 0]));
  const somar = (pesos, fator = 1) => {
    for (const [area, n] of Object.entries(pesos)) if (area in total) total[area] += n * fator;
  };
  form.querySelectorAll("input:checked[data-pesos], option:checked[data-pesos]").forEach(el => somar(lerPesos(el.dataset.pesos)));
  form.querySelectorAll('input[type="range"][data-pesos], input[type="number"][data-pesos]').forEach(el => {
    const min = Number(el.min || 0), max = Number(el.max || 1);
    somar(lerPesos(el.dataset.pesos), max > min ? (Number(el.value) - min) / (max - min) : 0);
  });
  const maior = Math.max(0, ...Object.values(total));
  return AREAS.map((a, i) => ({ a, v: total[a.codigo], i }))
    .sort((x, y) => y.v - x.v || x.i - y.i)
    .map(({ a, v }, n) => ({ area_code: a.codigo, area_label: a.nome, score: maior > 0 ? Math.max(0, v) / maior : 0, rank: n + 1 }));
}

async function calcularResultado(form) {
  // checkbox vai sempre como lista, mesmo com uma opção marcada
  const multiplos = new Set([...form.querySelectorAll('input[type="checkbox"]')].map(c => c.name));
  const respostas = Object.entries(estado.respostas).map(([question_id, value]) =>
    ({ question_id, value: multiplos.has(question_id) ? [].concat(value) : value }));
  if (cfg.pontuacao === "api") {
    const r = await postar(`${cfg.api}/vocational/submissions`, {
      session_id: estado.sessao,
      questionnaire_id: form.dataset.questionnaireId || "sem-id",
      questionnaire_version: form.dataset.questionnaireVersion || "sem-versao",
      answers: respostas,
      locale: "pt-BR",
    });
    return { ...r, demonstracao: false };
  }
  if (!form.querySelector("[data-pesos]")) throw new Error('o formulário não tem data-pesos; use pontuacao: "api"');
  return { affinities: pontuarPorPesos(form), disclaimer: AVISO, demonstracao: true };
}

// fontes do trilha.json
// Numera as referências na ordem em que aparecem na etapa. As marcas são botões
// (e não links "#...") porque o "#" já é usado pelas rotas da jornada.
function citador(refs) {
  const ordem = [];
  const numero = id => {
    if (!refs[id]) return null;
    if (!ordem.includes(id)) ordem.push(id);
    return ordem.indexOf(id) + 1;
  };
  const botao = id => {
    const n = numero(id);
    return n ? `<button type="button" class="ref" data-ref="${esc(id)}" aria-label="Referência ${n}">[${n}]</button>` : "";
  };
  return {
    numero,
    botao,
    marcas: (ids = []) => ids.map(botao).join(""),
    lista: () => `<section class="refs" aria-labelledby="refs-titulo">
      <h2 id="refs-titulo">Referências</h2>
      <ol>${ordem.map(id => {
        const r = refs[id];
        return `<li data-ref-item="${esc(id)}" tabindex="-1">${esc(r.citacao)}
          Disponível em: <a href="${esc(urlSegura(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.url)}</a>.
          ${r.acesso ? `Acesso em ${dataBR(r.acesso)}.` : ""}</li>`;
      }).join("")}</ol></section>`,
  };
}

// "DUNLOSKY, J.; RAWSON, K. A.; ... 2013" -> "DUNLOSKY et al., 2013" (citação curta no estilo ABNT)
function citacaoCurta(citacao) {
  const autores = citacao.split(/[a-zà-ú]/)[0].split(";").map(p => p.split(/[.,]/)[0].trim()).filter(Boolean);
  const anos = citacao.split("Disponível")[0].match(/\b(19|20)\d{2}\b/g) || [];
  const nome = autores.length > 3 ? `${autores[0]} et al.` : autores.join("; ");
  return `${nome}${anos.length ? ", " + anos[anos.length - 1] : ""}`;
}

function ativarReferencias(no) {
  no.addEventListener("click", e => {
    const b = e.target.closest(".ref");
    if (!b) return;
    const item = no.querySelector(`[data-ref-item="${b.dataset.ref}"]`);
    if (!item) return;
    item.scrollIntoView({ behavior: semMovimento ? "auto" : "smooth", block: "center" });
    item.focus({ preventScroll: true });
    item.classList.add("alvo");
    setTimeout(() => item.classList.remove("alvo"), 2000);
  });
}

function linkRecurso(r) {
  return `<a href="${esc(urlSegura(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.nome)}<span class="visually-hidden"> (abre em nova aba)</span></a>`;
}

const rodapeConteudo = c => `<p class="fine">${esc(c.aviso || "")}${c.revisado_em ? ` Revisado em ${dataBR(c.revisado_em)}.` : ""}</p>`;

// etapas
const ETAPA = {};

ETAPA.inicio = () => {
  const andamento = estado.iniciado && !estado.concluido;
  const no = html(`<section class="v-inicio">
    <p class="kicker">Orientação vocacional</p>
    <h1 class="display">Descubra com o que você mais combina <em>e o que esperar da área de TI</em>.</h1>
    <p class="lead">Responda a algumas perguntas sobre seus interesses e veja na hora suas áreas de afinidade.
      Depois, veja dados do Censo da Educação Superior e um caminho para começar a estudar.</p>
    <ol class="preview">
      <li><span class="n">1</span><div><strong>Responda</strong><span>Perguntas rápidas sobre o que você gosta de fazer.</span></div></li>
      <li><span class="n">2</span><div><strong>Descubra</strong><span>Suas áreas de maior afinidade, na hora.</span></div></li>
      <li><span class="n">3</span><div><strong>Planeje</strong><span>Dados de trancamento, competências e por onde começar.</span></div></li>
    </ol>
    <p class="fine">É uma ferramenta de orientação, não um teste psicológico. Não pedimos nome nem e-mail:
      as respostas ficam só nesta aba do navegador${cfg.pontuacao === "api" ? " e são enviadas apenas para calcular o resultado" : ""}.</p>
    ${andamento ? `<p class="resume">Você já começou. <button type="button" class="link" data-acao="zerar">Recomeçar do zero</button></p>` : ""}
  </section>`);
  no.querySelector('[data-acao="zerar"]')?.addEventListener("click", () => { recomecar(); rota(); });
  return {
    no,
    voltar: false,
    principal: {
      texto: andamento ? "Continuar de onde parei" : "Começar",
      acao: () => {
        if (!estado.iniciado) {
          estado.iniciado = true;
          estado.sessao = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
          salvar();
        }
        ir(andamento ? maisAvancada() : "formulario");
      },
    },
  };
};

ETAPA.formulario = async () => {
  const no = html(`<section class="v-form">
    <div class="form-head"><p class="kicker" id="q-contador">Carregando perguntas…</p><div class="q-dots" aria-hidden="true"></div></div>
    <div id="form-lugar"><div class="skeleton" style="height:12rem"></div></div>
  </section>`);
  const lugar = no.querySelector("#form-lugar");
  const t = { no, principal: { texto: "Próxima pergunta" } };
  try {
    formulario ??= await carregarFormulario();
  } catch (e) {
    lugar.innerHTML = `<div class="error"><strong>O formulário não carregou.</strong> ${esc(e.message)}.
      <button type="button" class="link">Tentar de novo</button></div>`;
    lugar.querySelector("button").addEventListener("click", rota);
    t.principal = null;
    return t;
  }
  const { form, paginas } = formulario;
  lugar.replaceChildren(form);
  const total = paginas.length;
  estado.pagina = Math.min(estado.pagina, total - 1);

  const verPagina = (direcao = 0) => {
    const i = estado.pagina;
    paginas.forEach((p, k) => { p.hidden = total > 1 && k !== i; p.classList.remove("entra-frente", "entra-tras"); });
    if (direcao && !semMovimento) paginas[i].classList.add(direcao > 0 ? "entra-frente" : "entra-tras");
    no.querySelector("#q-contador").textContent = total > 1 ? `Pergunta ${i + 1} de ${total}` : "Suas respostas";
    no.querySelector(".q-dots").innerHTML = paginas.map((_, k) => `<span class="${k < i ? "feita" : k === i ? "agora" : ""}"></span>`).join("");
    t.principal.texto = i === total - 1 ? "Ver meu resultado" : "Próxima pergunta";
    atualizarBotoes();
    if (direcao) {
      const legenda = paginas[i].querySelector("legend");
      if (legenda) { legenda.tabIndex = -1; legenda.focus({ preventScroll: true }); }
      aviso.textContent = no.querySelector("#q-contador").textContent;
      subir();
    }
  };

  t.voltar = () => {
    if (estado.pagina > 0) { estado.pagina--; salvar(); verPagina(-1); } else ir("inicio");
  };
  t.principal.acao = async () => {
    const pag = paginas[estado.pagina];
    const invalido = validar(pag);
    if (invalido) { invalido.focus(); return; }
    if (estado.pagina < total - 1) { estado.pagina++; salvar(); verPagina(1); return; }
    carregando(true, "Calculando…");
    try {
      estado.respostas = lerRespostas(form);
      estado.resultado = await calcularResultado(form);
      salvar();
      ir("resultado");
    } catch (e) {
      const erro = pag.querySelector(".jf-erro");
      erro.hidden = false;
      erro.textContent = `Não foi possível calcular o resultado: ${e.message}`;
    } finally {
      carregando(false);
      atualizarBotoes();
    }
  };
  t.aoMostrar = () => verPagina(0);
  return t;
};

ETAPA.resultado = () => {
  const r = estado.resultado;
  const no = html(`<section class="v-resultado">
    ${r.demonstracao ? `<p class="note demo"><span class="kicker">Demonstração</span>
      Resultado calculado com os pesos do formulário fictício. Não é o algoritmo oficial.</p>` : ""}
    <p class="kicker">Seu resultado</p>
    <h1 class="display">Sua maior afinidade é com <em>${esc(nomeArea(lider()))}</em>.</h1>
    <ol class="afinidades" aria-label="Áreas em ordem de afinidade">${r.affinities.map((a, i) => {
      const area = areaDados(a.area_code);
      return `<li style="--i:${i}"><span class="pos">${a.rank}º</span><span class="nome">${esc(nomeArea(a))}</span>
        <span class="barra"><span style="--w:${a.score};${area ? `--c:var(--s-${area})` : ""}"></span></span>
        <span class="val">${Math.round(a.score * 100)}</span></li>`;
    }).join("")}</ol>
    <p class="fine">Pontuação relativa: a área com mais afinidade vale 100. ${esc(r.disclaimer || AVISO)}</p>
    <p><button type="button" class="link">Refazer o formulário</button></p>
  </section>`);
  no.querySelector(".link").addEventListener("click", () => {
    estado.resultado = null;
    estado.pagina = 0;
    salvar();
    ir("formulario");
  });
  return {
    no,
    voltar: () => ir("formulario"),
    principal: { texto: "Continuar", acao: () => ir("interesse") },
    aoMostrar: () => requestAnimationFrame(() => no.classList.add("pronto")),
  };
};

ETAPA.interesse = () => {
  const lead = lider();
  const no = html(`<section class="v-interesse">
    <p class="kicker">Uma pergunta rápida</p>
    <h1 class="display">Você tem interesse em cursar uma graduação na área de TI?</h1>
    <p class="lead">${areaDados(lead?.area_code) === "TI"
      ? "Seu resultado aponta afinidade com Tecnologia da Informação."
      : `Seu resultado aponta mais afinidade com ${esc(nomeArea(lead))}. Tudo bem: você pode seguir e conhecer a área mesmo assim.`}</p>
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
  const opcoes = no.querySelectorAll("input");
  opcoes.forEach(op => {
    op.checked = op.value === estado.interesse;
    op.addEventListener("change", () => {
      estado.interesse = op.value;
      salvar();
      atualizarBotoes();
      // registro anônimo, só se o endpoint estiver configurado
      if (cfg.endpoints.interesse) postar(cfg.endpoints.interesse, { session_id: estado.sessao, interest: op.value }).catch(() => {});
    });
  });
  return {
    no,
    principal: {
      texto: "Continuar",
      bloqueado: () => !estado.interesse,
      dica: "Escolha uma das opções para continuar.",
      aoBloquear: () => opcoes[0].focus(),
      acao: () => ir("projeto"),
    },
  };
};

ETAPA.projeto = () => {
  const p = cfg.projeto;
  const no = html(`<section class="v-projeto">
    <p class="kicker">Projeto de permanência</p>
    <h1 class="display">Um projeto para ajudar estudantes de TI a seguir no curso</h1>
    <p class="lead">${esc(p.descricao || "")}</p>
    <p class="saiba">${p.saibaMaisUrl
      ? `<a class="btn ghost" href="${esc(urlSegura(p.saibaMaisUrl))}" target="_blank" rel="noopener noreferrer">Quero saber mais<span class="visually-hidden"> (abre em nova aba)</span></a>`
      : "Em breve a equipe vai divulgar como participar."}</p>
    <p class="fine">Esta página não coleta nenhum dado pessoal.</p>
  </section>`);
  return { no, principal: { texto: "Continuar", acao: () => ir("dados") } };
};

ETAPA.dados = () => {
  const area = areaDados(lider()?.area_code);
  const destaque = area && area !== "TI" ? area : null;
  const no = html(`<section class="v-dados">
    <p class="kicker">O que dizem os dados · Censo da Educação Superior (INEP)</p>
    <h1 class="display" id="d-titulo">Trancamento no ensino superior</h1>
    <p class="lead" id="d-sub"><span class="skeleton-line"></span></p>
    <figure class="fig">
      <figcaption><span class="kicker">Figura 1</span><h2>Taxa de trancamento por área, ano a ano</h2>
        <p>${destaque ? `Em destaque: TI e sua área de maior afinidade (${esc(NOME_AREA[destaque])}).` : "TI em destaque."} Toque ou passe o mouse para ver cada ano.</p></figcaption>
      <ul class="legend">${legendaHTML()}</ul>
      <div class="chart" id="d-linhas"><div class="skeleton" style="height:16rem"></div></div>
      <details><summary>Ver os dados em tabela</summary><div class="table-wrap" id="d-t1"></div></details>
    </figure>
    <figure class="fig">
      <figcaption><span class="kicker">Figura 2</span><h2>Consolidado do período</h2>
        <p>Soma de todos os anos (vínculos-ano, não pessoas).</p></figcaption>
      <div class="chart" id="d-barras"></div>
      <details><summary>Ver os dados em tabela</summary><div class="table-wrap" id="d-t2"></div></details>
    </figure>
    <p class="source">Fonte: INEP, microdados do Censo da Educação Superior. Cálculo próprio; não é estatística oficial.
      <a href="estatisticas.html">Explorar com filtros</a>.</p>
    <p class="note"><span class="kicker">Importante</span> Trancar não é o mesmo que evadir: no Censo do INEP são
      situações de vínculo diferentes. Nas próximas etapas, veja competências da área e materiais para começar.</p>
  </section>`);
  let dados = null;
  const desenhar = () => {
    if (!dados) return;
    const [anual, resumo] = dados;
    const anos = anual.meta.periodo.anos_com_dados;
    graficoLinhas(no.querySelector("#d-linhas"), anual.data, anos, { destaque, rotuloDestaque: "Sua área" });
    no.querySelector("#d-t1").innerHTML = tabelaAnual(anual.data, anos);
    graficoBarras(no.querySelector("#d-barras"), resumo.data, { destaque });
    no.querySelector("#d-t2").innerHTML = tabelaResumo(resumo.data);
  };
  const aoRedimensionar = adiar(desenhar, 150);
  return {
    no,
    principal: { texto: "Continuar", acao: () => ir("competencias") },
    aoMostrar: async () => {
      window.addEventListener("resize", aoRedimensionar);
      try {
        dados = await carregarEstatisticas();
        const [anual, , total] = dados;
        const anos = anual.meta.periodo.anos_com_dados;
        const ultimo = anos[anos.length - 1];
        const ti = anual.data.find(r => r.ano === ultimo && r.grupo_codigo === "TI");
        const media = total.data.find(r => r.ano === ultimo)?.taxa_trancamento;
        const comparacao = media == null ? "" :
          `, ${ti.taxa_trancamento > media ? "acima" : "abaixo"} da média de todas as áreas (${pct(media)})`;
        no.querySelector("#d-titulo").innerHTML =
          `Em ${ultimo}, <em class="num">${pct(ti.taxa_trancamento)}</em> dos vínculos em cursos de TI estavam trancados${comparacao}.`;
        no.querySelector("#d-sub").innerHTML =
          `São <strong>${compacto(ti.trancadas)}</strong> matrículas trancadas em <strong>${nf.format(ti.matriculas + ti.trancadas)}</strong> vínculos de TI no ano.`;
        no.querySelector("#d-linhas").replaceChildren();
        desenhar();
      } catch {
        no.querySelector("#d-sub").textContent = "";
        no.querySelector("#d-linhas").innerHTML = `<div class="error"><strong>Os dados não carregaram.</strong>
          Verifique se a API está rodando (<code>python -m evasao api</code>). Você pode continuar a jornada mesmo assim.</div>`;
      }
    },
    limpar: () => window.removeEventListener("resize", aoRedimensionar),
  };
};

ETAPA.competencias = () => {
  const no = html(`<section class="v-comp">
    <p class="kicker">Competências</p>
    <h1 class="display">Competências que você vai desenvolver em TI</h1>
    <p class="lead" id="c-intro"><span class="skeleton-line"></span></p>
    <div class="acc" id="c-lista"><div class="skeleton" style="height:14rem"></div></div>
    <div id="c-refs"></div>
  </section>`);
  ativarReferencias(no);
  return {
    no,
    principal: { texto: "Continuar", acao: () => ir("estudos") },
    aoMostrar: async () => {
      try {
        const c = await carregarConteudo();
        const cit = citador(c.referencias || {});
        no.querySelector("#c-intro").textContent = c.competencias.introducao;
        // montado na ordem da página para a numeração das fontes seguir a leitura
        no.querySelector("#c-lista").innerHTML = c.competencias.itens.map((it, i) => {
          const fontes = (it.fontes || []).filter(f => cit.numero(f.ref)).map(f =>
            `<li><span class="n">[${cit.numero(f.ref)}]</span> ${esc(f.trecho)} — ${esc(citacaoCurta(c.referencias[f.ref].citacao))}</li>`).join("");
          const recursos = (it.recursos || []).map(id => c.recursos[id]).filter(Boolean);
          return `<details class="acc-item" ${i === 0 ? "open" : ""}>
            <summary><span class="numeral">${i + 1}</span>
              <span class="acc-title"><span class="t">${esc(it.titulo)}</span><span class="s">${esc(it.resumo)}</span></span>
              <span class="chev" aria-hidden="true"></span></summary>
            <div class="acc-body">
              <div><span class="kicker">Por que importa</span><p>${esc(it.por_que_importa)}</p>
                ${fontes ? `<details class="fontes"><summary>Fontes</summary><ul>${fontes}</ul></details>` : ""}</div>
              <div><span class="kicker">Como desenvolver</span><ul>${(it.como_desenvolver || []).map(d =>
                `<li>${esc(d.texto)}${cit.marcas(d.fontes)}</li>`).join("")}</ul></div>
              ${recursos.length ? `<p class="practice">Para praticar: ${recursos.map(linkRecurso).join(" · ")}</p>` : ""}
            </div>
          </details>`;
        }).join("");
        no.querySelector("#c-refs").innerHTML = rodapeConteudo(c) + cit.lista();
      } catch (e) {
        no.querySelector("#c-intro").textContent = "";
        no.querySelector("#c-lista").innerHTML = `<div class="error">O conteúdo não carregou (${esc(e.message)}).</div>`;
      }
    },
  };
};

ETAPA.estudos = () => {
  const frase = {
    sim: "Dá para começar antes mesmo da faculdade.",
    talvez: "Experimente as primeiras etapas antes de decidir.",
    nao: "Se um dia mudar de ideia, este é um ponto de partida.",
  }[estado.interesse] || "";
  const no = html(`<section class="v-estudos">
    <p class="kicker">Por onde começar</p>
    <h1 class="display">Sua trilha de estudos para começar em TI</h1>
    <p class="lead">${esc(frase)} <span id="e-intro"></span></p>
    <p class="como" id="e-como"></p>
    <ol class="timeline" id="e-etapas"><li><div class="skeleton" style="height:12rem"></div></li></ol>
    <div class="habits-wrap" id="e-habitos"></div>
    <aside class="band" id="e-trancar" hidden></aside>
    <div id="e-refs"></div>
  </section>`);
  ativarReferencias(no);
  return {
    no,
    principal: { texto: "Concluir jornada", acao: () => { estado.concluido = true; salvar(); ir("fim"); } },
    aoMostrar: async () => {
      try {
        const c = await carregarConteudo();
        const rec = c.recomendacoes;
        const cit = citador(c.referencias || {});
        no.querySelector("#e-intro").textContent = rec.introducao;
        no.querySelector("#e-como").textContent = rec.como_foi_montada || "";
        no.querySelector("#e-etapas").innerHTML = rec.etapas.map((e, i) => {
          const res = (e.recursos || []).map(id => c.recursos[id]).filter(Boolean);
          const item = r => `<li><a href="${esc(urlSegura(r.url))}" target="_blank" rel="noopener noreferrer">
            <span class="name">${esc(r.nome)}</span><span class="visually-hidden"> (abre em nova aba)</span>
            <span class="meta">${esc(r.idioma)} · ${esc(r.custo)}</span></a></li>`;
          const base = (e.base || []).filter(b => cit.numero(b.ref));
          return `<li class="step">
            <span class="dot" aria-hidden="true">${i + 1}</span>
            <h2>${esc(e.titulo)}</h2>
            <p class="when kicker">Sugestão: ${esc(e.quando)}</p>
            <ul class="obj">${e.objetivos.map(o => `<li>${esc(o)}</li>`).join("")}</ul>
            ${base.length ? `<div class="base">${base.map(b => `<p>Base: ${cit.botao(b.ref)} ${esc(b.trecho)}</p>`).join("")}</div>` : ""}
            <ul class="res">${res.slice(0, 2).map(item).join("")}</ul>
            ${res.length > 2 ? `<details class="more"><summary>Mais ${res.length - 2} ${res.length === 3 ? "material" : "materiais"}</summary>
              <ul class="res">${res.slice(2).map(item).join("")}</ul></details>` : ""}
          </li>`;
        }).join("");
        no.querySelector("#e-habitos").innerHTML = `<h2>${esc(rec.habitos.titulo)}</h2>
          <ul class="habits">${rec.habitos.itens.map(h => `<li>${esc(h.texto)}${cit.marcas(h.fontes)}</li>`).join("")}</ul>`;
        const t = rec.antes_de_trancar;
        const caixa = no.querySelector("#e-trancar");
        caixa.hidden = false;
        caixa.innerHTML = `<span class="kicker">Antes de decidir</span><h2>${esc(t.titulo)}</h2><p>${esc(t.texto)}</p>
          <ul>${t.itens.map(x => `<li>${esc(x.texto)}${cit.marcas(x.fontes)}</li>`).join("")}</ul>`;
        no.querySelector("#e-refs").innerHTML = rodapeConteudo(c) + cit.lista();
      } catch (e) {
        no.querySelector("#e-etapas").innerHTML = `<li><div class="error">O conteúdo não carregou (${esc(e.message)}).</div></li>`;
      }
    },
  };
};

ETAPA.fim = () => {
  const interesse = { sim: "Sim, quero cursar TI", talvez: "Talvez, ainda estou decidindo", nao: "Meu interesse é outra área" }[estado.interesse];
  const no = html(`<section class="v-fim">
    <p class="kicker">Jornada concluída</p>
    <h1 class="display">Bom começo! <em>O próximo passo é seu.</em></h1>
    <dl class="recap">
      <div><dt>Maior afinidade</dt><dd>${esc(nomeArea(lider()))}${estado.resultado?.demonstracao ? " <small>(demonstração)</small>" : ""}</dd></div>
      <div><dt>Interesse em TI</dt><dd>${esc(interesse || "—")}</dd></div>
    </dl>
    <div class="next-links">
      <a class="card-link" href="#/resultado"><span class="t">Rever meu resultado</span><span class="s">Suas áreas de afinidade</span></a>
      <a class="card-link" href="#/dados"><span class="t">Rever os dados</span><span class="s">Trancamento por área</span></a>
      <a class="card-link" href="#/estudos"><span class="t">Minha trilha de estudos</span><span class="s">Materiais e referências</span></a>
    </div>
    <p class="fine">Suas respostas estão só nesta aba do navegador e somem ao fechá-la.
      <button type="button" class="link">Apagar agora e recomeçar</button></p>
  </section>`);
  no.querySelector(".fine .link").addEventListener("click", () => { recomecar(); ir("inicio"); });
  return { no, voltar: () => ir("estudos"), principal: null };
};

rota();
