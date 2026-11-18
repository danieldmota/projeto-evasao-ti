// Gráficos em SVG (sem biblioteca), tabelas e acesso à API.
// Usado pela jornada (index.html) e pela página de estatísticas.

export const AREAS = [
  { codigo: "TI", nome: "Tecnologia da Informação" },
  { codigo: "EXATAS_EXCETO_TI", nome: "Exatas e Tecnologia (exceto TI)" },
  { codigo: "NATUREZA_SAUDE", nome: "Natureza e Saúde" },
  { codigo: "GESTAO_NEGOCIOS", nome: "Gestão e Negócios" },
  { codigo: "HUMANAS_SOCIAIS_ARTES", nome: "Humanas, Sociais e Artes" },
];
export const NOME_AREA = Object.fromEntries(AREAS.map(a => [a.codigo, a.nome]));
const cor = codigo => `var(--s-${codigo})`;

export const nf = new Intl.NumberFormat("pt-BR");
export const pct = (v, casas = 1) => v == null ? "sem dado" :
  (v * 100).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }) + "%";
export const compacto = v => v == null ? "sem dado" :
  new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(v);
export const esc = s => String(s ?? "").replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function svg(tag, attrs, pai) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (pai) pai.appendChild(n);
  return n;
}

const passoEixo = max => max > 0.3 ? 0.1 : 0.05;
const tetoEixo = v => Math.max(passoEixo(v), Math.ceil(v / passoEixo(v)) * passoEixo(v));

function caixaDica(container) {
  let dica = container.querySelector(".tooltip");
  if (!dica) {
    dica = document.createElement("div");
    dica.className = "tooltip";
    dica.setAttribute("role", "status");
    container.appendChild(dica);
  }
  return dica;
}

export function legendaHTML() {
  return AREAS.map(a => `<li><span class="sw" style="background:${cor(a.codigo)}"></span>${esc(a.nome)}</li>`).join("");
}

// Linhas da taxa por ano. Ano sem dado vira lacuna (nunca zero).
// opcoes.destaque = área destacada junto com TI; opcoes.rotuloDestaque = texto do rótulo.
export function graficoLinhas(container, linhas, anos, opcoes = {}) {
  container.querySelectorAll("svg").forEach(n => n.remove());
  const dica = caixaDica(container);
  const destaque = NOME_AREA[opcoes.destaque] ? opcoes.destaque : null;
  const fortes = new Set(["TI", destaque].filter(Boolean));
  const W = Math.max(280, container.clientWidth);
  const estreito = W < 560;
  const H = estreito ? 260 : 340;
  const m = { top: 14, right: estreito ? 70 : 110, bottom: 30, left: 42 };
  const iw = W - m.left - m.right, ih = H - m.top - m.bottom;

  const porChave = new Map(linhas.map(r => [`${r.ano}|${r.grupo_codigo}`, r]));
  const taxa = (ano, codigo) => porChave.get(`${ano}|${codigo}`)?.taxa_trancamento;
  const valores = linhas.filter(r => NOME_AREA[r.grupo_codigo]).map(r => r.taxa_trancamento).filter(v => v != null);
  const yMax = tetoEixo(Math.max(0.01, ...valores));
  const x = i => anos.length === 1 ? iw / 2 : (i / (anos.length - 1)) * iw;
  const y = v => ih - (v / yMax) * ih;

  const el = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Gráfico de linhas: taxa de trancamento por ano e área" }, container);
  const g = svg("g", { transform: `translate(${m.left},${m.top})` }, el);

  for (let t = 0; t <= yMax + 1e-9; t += passoEixo(yMax)) {
    svg("line", { x1: 0, x2: iw, y1: y(t), y2: y(t), stroke: "var(--grid)" }, g);
    svg("text", { x: -10, y: y(t), "text-anchor": "end", "dominant-baseline": "middle", fill: "var(--ink-3)", "font-size": 12 }, g)
      .textContent = Math.round(t * 100) + "%";
  }
  const pulo = estreito ? Math.ceil(anos.length / 5) : (anos.length > 10 ? 2 : 1);
  anos.forEach((ano, i) => {
    if (i % pulo !== 0 && i !== anos.length - 1) return;
    svg("text", { x: x(i), y: ih + 22, "text-anchor": "middle", fill: "var(--ink-3)", "font-size": 12 }, g).textContent = ano;
  });

  const pontas = [];
  // as linhas em destaque são desenhadas por último para ficar por cima
  const ordem = [...AREAS].sort((a, b) => fortes.has(a.codigo) - fortes.has(b.codigo));
  for (const a of ordem) {
    let d = "", caneta = false, ultimo = null;
    anos.forEach((ano, i) => {
      const v = taxa(ano, a.codigo);
      if (v == null) { caneta = false; return; }
      d += `${caneta ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      caneta = true; ultimo = { i, v };
    });
    if (!d) continue;
    const forte = fortes.has(a.codigo);
    svg("path", { d, fill: "none", stroke: cor(a.codigo), "stroke-width": forte ? 3 : 2,
      "stroke-linejoin": "round", "stroke-linecap": "round", opacity: destaque && !forte ? 0.55 : 1 }, g);
    svg("circle", { cx: x(ultimo.i), cy: y(ultimo.v), r: forte ? 5 : 4, fill: cor(a.codigo), stroke: "var(--paper)", "stroke-width": 2 }, g);
    if (forte) pontas.push({ codigo: a.codigo, x: x(ultimo.i), y: y(ultimo.v), v: ultimo.v });
  }
  // rótulo direto só nas séries em destaque, afastando se ficarem colados
  pontas.sort((a, b) => a.y - b.y).forEach((p, i) => {
    p.ly = i > 0 && p.y - pontas[i - 1].ly < 16 ? pontas[i - 1].ly + 16 : p.y;
    const nome = p.codigo === "TI" ? "TI" : (opcoes.rotuloDestaque || "Sua área");
    svg("text", { x: p.x + 12, y: p.ly, "dominant-baseline": "middle", fill: "var(--ink)", "font-size": 13, "font-weight": 700 }, g)
      .textContent = `${nome} ${pct(p.v)}`;
  });

  const guia = svg("line", { y1: 0, y2: ih, stroke: "var(--ink-3)", visibility: "hidden" }, g);
  const pontos = svg("g", { visibility: "hidden" }, g);
  const area = svg("rect", { x: -m.left, y: 0, width: iw + m.left + 20, height: ih, fill: "transparent" }, g);

  const mover = evt => {
    const caixa = el.getBoundingClientRect();
    const escala = W / caixa.width;
    const px = (evt.clientX - caixa.left) * escala - m.left;
    const i = Math.max(0, Math.min(anos.length - 1, Math.round(anos.length === 1 ? 0 : (px / iw) * (anos.length - 1))));
    const ano = anos[i];
    guia.setAttribute("x1", x(i)); guia.setAttribute("x2", x(i));
    guia.setAttribute("visibility", "visible");
    pontos.replaceChildren();
    const itens = AREAS.map(a => ({ a, v: taxa(ano, a.codigo) })).sort((p, q) => (q.v ?? -1) - (p.v ?? -1));
    for (const { a, v } of itens) {
      if (v != null) svg("circle", { cx: x(i), cy: y(v), r: 4, fill: cor(a.codigo), stroke: "var(--paper)", "stroke-width": 2 }, pontos);
    }
    pontos.setAttribute("visibility", "visible");
    dica.innerHTML = `<div class="t-title">${ano}</div>` + itens.map(({ a, v }) =>
      `<div class="row"><span><i class="k" style="background:${cor(a.codigo)}"></i>${esc(a.nome)}</span><strong>${pct(v)}</strong></div>`).join("");
    const esq = (m.left + x(i)) / escala;
    dica.style.left = Math.max(0, esq > container.clientWidth / 2 ? esq - dica.offsetWidth - 14 : esq + 14) + "px";
    dica.style.top = (m.top / escala) + "px";
    dica.classList.add("on");
  };
  area.addEventListener("pointermove", mover);
  area.addEventListener("pointerdown", mover);
  area.addEventListener("pointerleave", () => {
    guia.setAttribute("visibility", "hidden");
    pontos.setAttribute("visibility", "hidden");
    dica.classList.remove("on");
  });
}

// Barras horizontais do período inteiro. opcoes.destaque marca "sua maior afinidade".
export function graficoBarras(container, linhas, opcoes = {}) {
  container.querySelectorAll("svg").forEach(n => n.remove());
  const dica = caixaDica(container);
  const dados = linhas.filter(r => NOME_AREA[r.grupo_codigo] && r.taxa_trancamento != null)
    .sort((a, b) => b.taxa_trancamento - a.taxa_trancamento);
  const W = Math.max(280, container.clientWidth);
  const estreito = W < 560;
  const largRotulo = estreito ? 0 : 210;
  const barra = 22, espaco = estreito ? 34 : 16;
  const m = { top: 4, right: opcoes.destaque && !estreito ? 150 : 64, bottom: 4, left: largRotulo };
  const iw = W - m.left - m.right;
  const alturaLinha = barra + espaco;
  const H = m.top + m.bottom + dados.length * alturaLinha;
  const xMax = tetoEixo(Math.max(0.01, ...dados.map(d => d.taxa_trancamento)));

  const el = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Gráfico de barras: taxa de trancamento consolidada por área" }, container);
  const g = svg("g", { transform: `translate(${m.left},${m.top})` }, el);
  svg("line", { x1: 0, x2: 0, y1: 0, y2: H - m.top - m.bottom, stroke: "var(--rule)" }, g);

  dados.forEach((d, i) => {
    const topo = i * alturaLinha + (estreito ? 18 : espaco / 2);
    const w = Math.max(2, (d.taxa_trancamento / xMax) * iw);
    const r = Math.min(4, w / 2);
    const forte = d.grupo_codigo === "TI" || d.grupo_codigo === opcoes.destaque;
    const minha = d.grupo_codigo === opcoes.destaque;
    svg("path", { fill: cor(d.grupo_codigo),
      d: `M0,${topo} H${w - r} Q${w},${topo} ${w},${topo + r} V${topo + barra - r} Q${w},${topo + barra} ${w - r},${topo + barra} H0 Z` }, g);

    const estiloNome = { fill: forte ? "var(--ink)" : "var(--ink-2)", "font-weight": forte ? 700 : 400 };
    svg("text", estreito
      ? { x: 0, y: topo - 6, "font-size": 12, ...estiloNome }
      : { x: -12, y: topo + barra / 2, "text-anchor": "end", "dominant-baseline": "middle", "font-size": 13, ...estiloNome }, g)
      .textContent = NOME_AREA[d.grupo_codigo] + (estreito && minha ? " · sua maior afinidade" : "");
    svg("text", { x: w + 8, y: topo + barra / 2, "dominant-baseline": "middle", fill: "var(--ink)", "font-size": 13, "font-weight": forte ? 700 : 400 }, g)
      .textContent = pct(d.taxa_trancamento);
    if (!estreito && minha) {
      svg("text", { x: w + 58, y: topo + barra / 2, "dominant-baseline": "middle", fill: "var(--ink-2)", "font-size": 12, "font-style": "italic" }, g)
        .textContent = "← sua maior afinidade";
    }

    const area = svg("rect", { x: -largRotulo, y: topo - espaco / 2, width: W, height: alturaLinha, fill: "transparent" }, g);
    const mostrar = evt => {
      dica.innerHTML = `<div class="t-title">${esc(NOME_AREA[d.grupo_codigo])}</div>
        <div class="row"><span>Taxa de trancamento</span><strong>${pct(d.taxa_trancamento)}</strong></div>
        <div class="row"><span>Trancadas</span><strong>${nf.format(d.trancadas)}</strong></div>
        <div class="row"><span>Matrículas</span><strong>${nf.format(d.matriculas)}</strong></div>`;
      const caixa = container.getBoundingClientRect();
      let esq = evt.clientX - caixa.left + 14;
      if (esq + dica.offsetWidth > caixa.width) esq = Math.max(0, evt.clientX - caixa.left - dica.offsetWidth - 14);
      dica.style.left = esq + "px";
      dica.style.top = (evt.clientY - caixa.top + 14) + "px";
      dica.classList.add("on");
    };
    area.addEventListener("pointermove", mostrar);
    area.addEventListener("pointerdown", mostrar);
    area.addEventListener("pointerleave", () => dica.classList.remove("on"));
  });
}

export function tabelaAnual(linhas, anos) {
  const porChave = new Map(linhas.map(r => [`${r.ano}|${r.grupo_codigo}`, r]));
  return `<table><thead><tr><th>Ano</th>${AREAS.map(a => `<th>${esc(a.nome)}</th>`).join("")}</tr></thead><tbody>` +
    anos.map(ano => `<tr><td>${ano}</td>${AREAS.map(a =>
      `<td>${pct(porChave.get(`${ano}|${a.codigo}`)?.taxa_trancamento)}</td>`).join("")}</tr>`).join("") +
    "</tbody></table>";
}

export function tabelaResumo(linhas) {
  return `<table><thead><tr><th>Área</th><th>Matrículas</th><th>Trancadas</th><th>Taxa</th></tr></thead><tbody>` +
    linhas.filter(r => NOME_AREA[r.grupo_codigo]).map(r => `<tr><td>${esc(NOME_AREA[r.grupo_codigo])}</td>
      <td>${nf.format(r.matriculas ?? 0)}</td><td>${nf.format(r.trancadas ?? 0)}</td><td>${pct(r.taxa_trancamento)}</td></tr>`).join("") +
    "</tbody></table>";
}

// GET na API; parâmetros vazios não são enviados
export function criarApi(base) {
  base = base.replace(/\/$/, "");
  return async (caminho, filtros = {}) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(filtros)) if (v !== "" && v != null) qs.append(k, v);
    const resp = await fetch(base + caminho + (qs.toString() ? "?" + qs : ""));
    const corpo = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(corpo?.error?.message || `HTTP ${resp.status}`);
    return corpo;
  };
}
