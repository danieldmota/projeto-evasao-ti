/* Lógica pura da jornada (sem DOM): etapas, regras de acesso, estado, coleta de
   respostas e pontuação provisória por pesos. Testada com `node --test tests/js`.

   Privacidade: o estado da jornada NUNCA guarda nome ou e-mail. A participação no
   projeto é registrada só como status ("enviada" | "demonstracao" | "recusada"). */

export const STEPS = [
  { id: "inicio", titulo: "Boas-vindas", curto: "Início" },
  { id: "formulario", titulo: "Seus interesses", curto: "Formulário" },
  { id: "resultado", titulo: "Suas áreas de afinidade", curto: "Resultado" },
  { id: "interesse", titulo: "Interesse em TI", curto: "Interesse em TI" },
  { id: "projeto", titulo: "Projeto de permanência", curto: "Participação" },
  { id: "dados", titulo: "O que dizem os dados", curto: "Dados" },
  { id: "competencias", titulo: "Competências em TI", curto: "Competências" },
  { id: "estudos", titulo: "Por onde começar", curto: "Estudos" },
];
export const FINAL = "fim";
const IDS = STEPS.map(s => s.id);

export const INTEREST_OPTIONS = ["sim", "talvez", "nao"];
export const PARTICIPATION_STATUS = ["enviada", "demonstracao", "recusada"];

export function initialState() {
  return {
    versao: 1,
    session_id: null,
    iniciado: false,
    respostas: {},          // { question_id: valor }
    paginaFormulario: 0,
    formularioConcluido: false,
    resultado: null,        // VocationalResult (+ demonstracao: bool)
    interesse: null,        // "sim" | "talvez" | "nao"
    participacao: null,     // status, nunca dados pessoais
    concluido: false,
  };
}

/** Normaliza um estado lido do armazenamento: só chaves conhecidas e valores válidos. */
export function sanitizeState(raw) {
  const base = initialState();
  if (!raw || typeof raw !== "object" || raw.versao !== base.versao) return base;
  const out = { ...base };
  for (const k of Object.keys(base)) if (k in raw) out[k] = raw[k];
  if (typeof out.respostas !== "object" || out.respostas === null || Array.isArray(out.respostas)) out.respostas = {};
  if (!INTEREST_OPTIONS.includes(out.interesse)) out.interesse = null;
  if (!PARTICIPATION_STATUS.includes(out.participacao)) out.participacao = null;
  if (!Number.isInteger(out.paginaFormulario) || out.paginaFormulario < 0) out.paginaFormulario = 0;
  if (out.resultado && !Array.isArray(out.resultado.affinities)) out.resultado = null;
  for (const k of ["iniciado", "concluido", "formularioConcluido"]) out[k] = Boolean(out[k]);
  if (!out.resultado) out.formularioConcluido = false;   // resultado é o que comprova o envio
  return out;
}

/** Pré-requisito de cada etapa (true = pode entrar). */
const REQUIRES = {
  inicio: () => true,
  formulario: s => s.iniciado,
  resultado: s => Boolean(s.resultado),
  interesse: s => Boolean(s.resultado),
  projeto: s => s.interesse !== null,
  dados: s => s.participacao !== null,
  competencias: s => s.participacao !== null,
  estudos: s => s.participacao !== null,
  [FINAL]: s => s.concluido,
};

export function canEnter(stepId, state) {
  const rule = REQUIRES[stepId];
  return rule ? rule(state) : false;
}

/** Última etapa que o usuário pode acessar com o estado atual. */
export function furthestAllowed(state) {
  if (canEnter(FINAL, state)) return FINAL;
  let last = IDS[0];
  for (const id of IDS) {
    if (canEnter(id, state)) last = id; else break;
  }
  return last;
}

/** Resolve a rota pedida: se bloqueada (ou desconhecida), devolve a mais avançada permitida. */
export function resolveRoute(requested, state) {
  if ((IDS.includes(requested) || requested === FINAL) && canEnter(requested, state)) return requested;
  return furthestAllowed(state);
}

/** A etapa atual permite avançar? */
export function canContinue(stepId, state) {
  switch (stepId) {
    case "formulario": return state.formularioConcluido && Boolean(state.resultado);
    case "interesse": return state.interesse !== null;
    case "projeto": return state.participacao !== null;
    default: return true;
  }
}

export function nextStepId(id) {
  const i = IDS.indexOf(id);
  if (i === -1) return null;
  return i === IDS.length - 1 ? FINAL : IDS[i + 1];
}
export function prevStepId(id) {
  if (id === FINAL) return IDS[IDS.length - 1];
  const i = IDS.indexOf(id);
  return i > 0 ? IDS[i - 1] : null;
}
export function stepIndex(id) { return IDS.indexOf(id); }

/** Estado visual de cada etapa no indicador de progresso. */
export function stepStatus(stepId, currentId, state) {
  if (stepId === currentId) return "atual";
  const done = currentId === FINAL || stepIndex(stepId) < stepIndex(currentId);
  if (done && canEnter(stepId, state)) return "concluida";
  return canEnter(stepId, state) ? "disponivel" : "bloqueada";
}

/**
 * Converte pares [nome, valor] (FormData) em respostas.
 * Nomes repetidos (checkbox) viram lista; nomes em `numericNames` viram número.
 */
export function collectAnswers(entries, numericNames = new Set()) {
  const map = new Map();
  for (const [name, raw] of entries) {
    if (!name) continue;
    const value = numericNames.has(name) && raw !== "" && !Number.isNaN(Number(raw)) ? Number(raw) : raw;
    if (map.has(name)) {
      const prev = map.get(name);
      map.set(name, Array.isArray(prev) ? [...prev, value] : [prev, value]);
    } else {
      map.set(name, value);
    }
  }
  return Object.fromEntries(map);
}

export function toSubmissionAnswers(respostas, multiNames = new Set()) {
  return Object.entries(respostas).map(([question_id, value]) => ({
    question_id,
    value: multiNames.has(question_id) && !Array.isArray(value) ? [value] : value,
  }));
}

/** "TI:2, EXATAS_EXCETO_TI:1" -> { TI: 2, EXATAS_EXCETO_TI: 1 } */
export function parseWeights(text) {
  const out = {};
  if (!text) return out;
  for (const part of String(text).split(",")) {
    const [k, v] = part.split(":").map(x => x && x.trim());
    const n = Number(v);
    if (k && Number.isFinite(n)) out[k] = (out[k] || 0) + n;
  }
  return out;
}

/**
 * Pontuação PROVISÓRIA por pesos declarados no próprio HTML do formulário.
 * `contributions`: lista de objetos de pesos (um por opção marcada; escalas já
 * multiplicadas pelo valor escolhido). `areas`: [{code, label}] na ordem de exibição.
 * Normaliza pela maior soma (a área líder fica com 1). Empates mantêm a ordem de `areas`.
 */
export function scoreByWeights(contributions, areas) {
  const totals = Object.fromEntries(areas.map(a => [a.code, 0]));
  for (const w of contributions) {
    for (const [code, n] of Object.entries(w)) if (code in totals) totals[code] += n;
  }
  const max = Math.max(0, ...Object.values(totals));
  const ranked = areas
    .map((a, i) => ({ area_code: a.code, area_label: a.label, raw: totals[a.code], i }))
    .sort((x, y) => y.raw - x.raw || x.i - y.i);
  return ranked.map((r, idx) => ({
    area_code: r.area_code,
    area_label: r.area_label,
    score: max > 0 ? Math.max(0, r.raw) / max : 0,
    rank: idx + 1,
  }));
}

export function progress(stepId) {
  const total = STEPS.length;
  const index = stepId === FINAL ? total : Math.max(0, IDS.indexOf(stepId));
  return { index, total, numero: Math.min(index + 1, total), fracao: index / total };
}
