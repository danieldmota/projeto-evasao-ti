/* Gráficos SVG sem dependências, compartilhados entre a jornada (index.html) e
   a página de estatísticas. Regras de visualização:
   - taxas são razão de somas vindas da API; ano sem dado = lacuna na linha, nunca zero;
   - paleta categórica fixa por entidade (TI é sempre azul), validada para daltonismo;
   - legenda + rótulo direto + tabela (as cores claras não têm 3:1 contra o fundo). */

export const SERIES = [
  { code: "TI", label: "Tecnologia da Informação" },
  { code: "EXATAS_EXCETO_TI", label: "Exatas e Tecnologia (exceto TI)" },
  { code: "NATUREZA_SAUDE", label: "Natureza e Saúde" },
  { code: "GESTAO_NEGOCIOS", label: "Gestão e Negócios" },
  { code: "HUMANAS_SOCIAIS_ARTES", label: "Humanas, Sociais e Artes" },
];
export const LABEL = Object.fromEntries(SERIES.map(s => [s.code, s.label]));
export const color = code => `var(--s-${code})`;

export const nf = new Intl.NumberFormat("pt-BR");
export const pct = (v, d = 1) => v == null ? "sem dado" :
  (v * 100).toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }) + "%";
export const compact = v => v == null ? "sem dado" :
  new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(v);
export const esc = s => String(s).replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const svgNS = "http://www.w3.org/2000/svg";
function el(tag, attrs = {}, parent) {
  const n = document.createElementNS(svgNS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}
function niceMax(v) {
  const step = v > 0.3 ? 0.1 : 0.05;
  return Math.max(step, Math.ceil(v / step) * step);
}
function ensureTooltip(container) {
  let tip = container.querySelector(".tooltip");
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "tooltip";
    tip.setAttribute("role", "status");
    container.appendChild(tip);
  }
  return tip;
}

export function legendHTML() {
  return SERIES.map(s =>
    `<li><span class="sw" style="background:${color(s.code)}"></span>${esc(s.label)}</li>`).join("");
}

/** Linhas anuais por segmento. opts.highlight = código do segmento a destacar (além de TI). */
export function renderLines(container, rows, years, opts = {}) {
  container.querySelectorAll("svg").forEach(n => n.remove());
  const tip = ensureTooltip(container);
  const hl = opts.highlight && LABEL[opts.highlight] ? opts.highlight : null;
  const strong = new Set(["TI", hl].filter(Boolean));
  const W = Math.max(280, container.clientWidth);
  const narrow = W < 560;
  const H = opts.height || (narrow ? 260 : 340);
  const m = { top: 14, right: narrow ? 70 : 110, bottom: 30, left: 42 };
  const iw = W - m.left - m.right, ih = H - m.top - m.bottom;

  const byKey = new Map(rows.map(r => [`${r.ano}|${r.grupo_codigo}`, r]));
  const values = rows.filter(r => LABEL[r.grupo_codigo])
    .map(r => r.taxa_trancamento).filter(v => v != null);
  const yMax = niceMax(Math.max(0.01, ...values));
  const x = i => years.length === 1 ? iw / 2 : (i / (years.length - 1)) * iw;
  const y = v => ih - (v / yMax) * ih;

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Gráfico de linhas: taxa de trancamento por ano e área" }, container);
  const g = el("g", { transform: `translate(${m.left},${m.top})` }, svg);

  const step = yMax > 0.3 ? 0.1 : 0.05;
  for (let t = 0; t <= yMax + 1e-9; t += step) {
    el("line", { x1: 0, x2: iw, y1: y(t), y2: y(t), stroke: "var(--grid)", "stroke-width": 1 }, g);
    const tx = el("text", { x: -10, y: y(t), "text-anchor": "end", "dominant-baseline": "middle",
      fill: "var(--ink-3)", "font-size": 12 }, g);
    tx.textContent = Math.round(t * 100) + "%";
  }
  const every = narrow ? Math.ceil(years.length / 5) : (years.length > 10 ? 2 : 1);
  years.forEach((yr, i) => {
    if (i % every !== 0 && i !== years.length - 1) return;
    const tx = el("text", { x: x(i), y: ih + 22, "text-anchor": "middle",
      fill: "var(--ink-3)", "font-size": 12 }, g);
    tx.textContent = yr;
  });

  const ends = [];
  const order = [...SERIES].sort((a, b) => strong.has(a.code) - strong.has(b.code));
  for (const s of order) {                       // destacados por último = por cima
    let d = "", pen = false, last = null;
    years.forEach((yr, i) => {
      const v = byKey.get(`${yr}|${s.code}`)?.taxa_trancamento;
      if (v == null) { pen = false; return; }    // lacuna, nunca zero
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true; last = { i, v };
    });
    if (!d) continue;
    const isStrong = strong.has(s.code);
    el("path", { d, fill: "none", stroke: color(s.code), "stroke-width": isStrong ? 3 : 2,
      "stroke-linejoin": "round", "stroke-linecap": "round",
      opacity: hl && !isStrong ? 0.55 : 1 }, g);
    if (last) {
      el("circle", { cx: x(last.i), cy: y(last.v), r: isStrong ? 5 : 4, fill: color(s.code),
        stroke: "var(--paper)", "stroke-width": 2 }, g);
      ends.push({ code: s.code, x: x(last.i), y: y(last.v), v: last.v });
    }
  }
  // rótulos diretos só das séries em destaque; afasta se colidirem
  const labels = ends.filter(e => strong.has(e.code)).sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++) {
    if (labels[i].y - labels[i - 1].y < 16) labels[i].ly = labels[i - 1].ly + 16;
  }
  labels.forEach(e => {
    const short = e.code === "TI" ? "TI" : (opts.highlightLabel || "Sua área");
    const t = el("text", { x: e.x + 12, y: e.ly ?? e.y, "dominant-baseline": "middle",
      fill: "var(--ink)", "font-size": 13, "font-weight": 700 }, g);
    t.textContent = `${short} ${pct(e.v)}`;
    e.ly = e.ly ?? e.y;
  });

  const cross = el("line", { y1: 0, y2: ih, stroke: "var(--ink-3)", "stroke-width": 1,
    visibility: "hidden" }, g);
  const dots = el("g", { visibility: "hidden" }, g);
  const hit = el("rect", { x: -m.left, y: 0, width: iw + m.left + 20, height: ih,
    fill: "transparent" }, g);

  const move = evt => {
    const pt = svg.getBoundingClientRect();
    const scale = W / pt.width;
    const px = (evt.clientX - pt.left) * scale - m.left;
    const i = Math.max(0, Math.min(years.length - 1,
      Math.round(years.length === 1 ? 0 : (px / iw) * (years.length - 1))));
    const yr = years[i];
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i));
    cross.setAttribute("visibility", "visible");
    dots.replaceChildren();
    const items = SERIES.map(s => ({ s, r: byKey.get(`${yr}|${s.code}`) }))
      .sort((a, b) => (b.r?.taxa_trancamento ?? -1) - (a.r?.taxa_trancamento ?? -1));
    for (const { s, r } of items) {
      if (r?.taxa_trancamento == null) continue;
      el("circle", { cx: x(i), cy: y(r.taxa_trancamento), r: 4, fill: color(s.code),
        stroke: "var(--paper)", "stroke-width": 2 }, dots);
    }
    dots.setAttribute("visibility", "visible");
    tip.innerHTML = `<div class="t-title">${yr}</div>` + items.map(({ s, r }) =>
      `<div class="row"><span><i class="k" style="background:${color(s.code)}"></i>${esc(s.label)}</span>
       <strong>${pct(r?.taxa_trancamento)}</strong></div>`).join("");
    const cw = container.clientWidth;
    const left = (m.left + x(i)) / scale;
    tip.style.left = Math.max(0, left > cw / 2 ? left - tip.offsetWidth - 14 : left + 14) + "px";
    tip.style.top = (m.top / scale) + "px";
    tip.classList.add("on");
  };
  const leave = () => {
    cross.setAttribute("visibility", "hidden");
    dots.setAttribute("visibility", "hidden");
    tip.classList.remove("on");
  };
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", leave);
}

/** Barras horizontais do consolidado. opts.highlight = segmento com marcação "sua afinidade". */
export function renderBars(container, rows, opts = {}) {
  container.querySelectorAll("svg").forEach(n => n.remove());
  const tip = ensureTooltip(container);
  const data = rows.filter(r => LABEL[r.grupo_codigo] && r.taxa_trancamento != null)
    .sort((a, b) => b.taxa_trancamento - a.taxa_trancamento);
  const W = Math.max(280, container.clientWidth);
  const narrow = W < 560;
  const labelW = narrow ? 0 : 210;
  const bar = 22, gap = narrow ? 34 : 16;
  const m = { top: 4, right: opts.highlight ? 150 : 64, bottom: 4, left: labelW };
  if (narrow) m.right = 64;
  const iw = W - m.left - m.right;
  const rowH = bar + gap;
  const H = m.top + m.bottom + data.length * rowH;
  const xMax = niceMax(Math.max(0.01, ...data.map(d => d.taxa_trancamento)));
  const xs = v => (v / xMax) * iw;

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Gráfico de barras: taxa de trancamento consolidada por área" }, container);
  const g = el("g", { transform: `translate(${m.left},${m.top})` }, svg);
  el("line", { x1: 0, x2: 0, y1: 0, y2: H - m.top - m.bottom, stroke: "var(--rule)" }, g);

  data.forEach((d, i) => {
    const top = i * rowH + (narrow ? 18 : gap / 2);
    const w = Math.max(2, xs(d.taxa_trancamento));
    const r = Math.min(4, w / 2);
    const p = `M0,${top} H${w - r} Q${w},${top} ${w},${top + r} V${top + bar - r} Q${w},${top + bar} ${w - r},${top + bar} H0 Z`;
    const strong = d.grupo_codigo === "TI" || d.grupo_codigo === opts.highlight;
    el("path", { d: p, fill: color(d.grupo_codigo) }, g);

    const name = el("text", narrow
      ? { x: 0, y: top - 6, fill: strong ? "var(--ink)" : "var(--ink-2)", "font-size": 12,
          "font-weight": strong ? 700 : 400 }
      : { x: -12, y: top + bar / 2, "text-anchor": "end", "dominant-baseline": "middle",
          fill: strong ? "var(--ink)" : "var(--ink-2)", "font-size": 13,
          "font-weight": strong ? 700 : 400 }, g);
    name.textContent = LABEL[d.grupo_codigo] +
      (narrow && d.grupo_codigo === opts.highlight ? " · sua maior afinidade" : "");

    const val = el("text", { x: w + 8, y: top + bar / 2, "dominant-baseline": "middle",
      fill: "var(--ink)", "font-size": 13, "font-weight": strong ? 700 : 400 }, g);
    val.textContent = pct(d.taxa_trancamento);
    if (!narrow && d.grupo_codigo === opts.highlight) {
      const tag = el("text", { x: w + 58, y: top + bar / 2, "dominant-baseline": "middle",
        fill: "var(--ink-2)", "font-size": 12, "font-style": "italic" }, g);
      tag.textContent = "← sua maior afinidade";
    }

    const hit = el("rect", { x: -labelW, y: top - gap / 2, width: W, height: rowH,
      fill: "transparent" }, g);
    const show = evt => {
      tip.innerHTML = `<div class="t-title">${esc(LABEL[d.grupo_codigo])}</div>
        <div class="row"><span>Taxa de trancamento</span><strong>${pct(d.taxa_trancamento)}</strong></div>
        <div class="row"><span>Trancadas</span><strong>${nf.format(d.trancadas)}</strong></div>
        <div class="row"><span>Matrículas</span><strong>${nf.format(d.matriculas)}</strong></div>`;
      const box = container.getBoundingClientRect();
      let left = evt.clientX - box.left + 14;
      if (left + tip.offsetWidth > box.width) left = Math.max(0, evt.clientX - box.left - tip.offsetWidth - 14);
      tip.style.left = left + "px";
      tip.style.top = (evt.clientY - box.top + 14) + "px";
      tip.classList.add("on");
    };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("pointerdown", show);
    hit.addEventListener("pointerleave", () => tip.classList.remove("on"));
  });
}

export function annualTable(rows, years) {
  const byKey = new Map(rows.map(r => [`${r.ano}|${r.grupo_codigo}`, r]));
  let h = `<table><thead><tr><th>Ano</th>${SERIES.map(s => `<th>${esc(s.label)}</th>`).join("")}</tr></thead><tbody>`;
  for (const yr of years) {
    h += `<tr><td>${yr}</td>${SERIES.map(s => `<td>${pct(byKey.get(`${yr}|${s.code}`)?.taxa_trancamento)}</td>`).join("")}</tr>`;
  }
  return h + "</tbody></table>";
}

export function summaryTable(rows) {
  const data = rows.filter(r => LABEL[r.grupo_codigo]);
  return `<table><thead><tr><th>Área</th><th>Matrículas</th><th>Trancadas</th><th>Taxa</th></tr></thead><tbody>` +
    data.map(r => `<tr><td>${esc(LABEL[r.grupo_codigo])}</td><td>${nf.format(r.matriculas ?? 0)}</td>
      <td>${nf.format(r.trancadas ?? 0)}</td><td>${pct(r.taxa_trancamento)}</td></tr>`).join("") +
    "</tbody></table>";
}

/** Cliente da API (GET), com mensagem de erro padronizada. */
export function apiClient(base) {
  const API = base.replace(/\/$/, "");
  return async function api(path, query = {}) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v === "" || v == null) continue;
      (Array.isArray(v) ? v : [v]).forEach(x => qs.append(k, x));
    }
    const r = await fetch(`${API}${path}${qs.toString() ? "?" + qs : ""}`);
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body?.error?.message || `HTTP ${r.status}`);
    return body;
  };
}
