/* Encaixe do formulário vocacional: carrega o HTML, divide em telas por <fieldset>,
   valida cada tela, lê e restaura respostas e calcula contribuições de pesos.
   O HTML do formulário é tratado como conteúdo do próprio projeto; mesmo assim,
   <script> e atributos de evento on* são removidos ao importar. */

import { collectAnswers, parseWeights } from "./core.js";

export async function loadForm(url) {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`não foi possível carregar o formulário (HTTP ${res.status})`);
  const parsed = new DOMParser().parseFromString(await res.text(), "text/html");
  const form = parsed.querySelector("form");
  if (!form) throw new Error("o arquivo do formulário não contém um <form>");
  form.querySelectorAll("script").forEach(s => s.remove());
  form.querySelectorAll("*").forEach(n => {
    for (const a of [...n.attributes]) if (/^on/i.test(a.name)) n.removeAttribute(a.name);
  });
  form.setAttribute("novalidate", "");
  return document.importNode(form, true);
}

export function pagesOf(form) {
  const fs = [...form.querySelectorAll(":scope > fieldset")];
  return fs.length ? fs : [form];
}

const fieldsOf = root => [...root.querySelectorAll("input, select, textarea")]
  .filter(el => el.name && !el.disabled && el.type !== "submit" && el.type !== "button");

/** Acessibilidade e realces genéricos (escala com valor visível, ids de erro). */
export function enhance(form) {
  let n = 0;
  pagesOf(form).forEach((page, i) => {
    page.classList.add("jf-page");
    const err = document.createElement("p");
    err.className = "jf-error";
    err.id = `jf-err-${i}`;
    err.setAttribute("role", "alert");
    err.hidden = true;
    // logo abaixo da pergunta (e do texto de ajuda), para ficar visível sem rolar
    const anchor = page.querySelector(":scope > .ajuda") || page.querySelector(":scope > legend");
    if (anchor) anchor.after(err); else page.prepend(err);
    fieldsOf(page).forEach(f => f.setAttribute("aria-describedby", err.id));
  });
  form.querySelectorAll('input[type="range"]').forEach(r => {
    const wrap = document.createElement("div");
    wrap.className = "jf-scale";
    const out = document.createElement("output");
    out.className = "jf-scale-value";
    out.id = `jf-out-${n++}`;
    const min = r.dataset.rotuloMin, max = r.dataset.rotuloMax;
    const ends = document.createElement("div");
    ends.className = "jf-scale-ends";
    ends.innerHTML = `<span>${min ? escapeText(min) : r.min}</span><span>${max ? escapeText(max) : r.max}</span>`;
    r.replaceWith(wrap);
    wrap.append(out, r, ends);
    if (!r.getAttribute("aria-label")) {
      const legend = r.closest("fieldset")?.querySelector("legend")?.textContent?.trim();
      if (legend) r.setAttribute("aria-label", legend);
    }
    const sync = () => {
      out.textContent = r.value;
      const t = (r.value - r.min) / ((r.max - r.min) || 1);
      r.style.setProperty("--t", t);
      r.setAttribute("aria-valuetext", `${r.value}${min && max ? ` (de ${min} a ${max})` : ""}`);
    };
    r.addEventListener("input", sync);
    sync();
  });
}

function escapeText(s) {
  const d = document.createElement("span");
  d.textContent = s;
  return d.innerHTML;
}

/** Valida uma tela. Retorna lista de mensagens (vazia = ok) e o primeiro campo inválido. */
export function validatePage(page) {
  const messages = [];
  let first = null;
  const seen = new Set();
  for (const f of fieldsOf(page)) {
    if (seen.has(f.name) && (f.type === "radio" || f.type === "checkbox")) continue;
    if (!f.checkValidity()) {
      seen.add(f.name);
      first ??= f;
      let msg = f.dataset.erro;
      if (!msg) {
        if (f.validity.valueMissing) msg = f.type === "radio" ? "Escolha uma opção para continuar." : "Preencha este campo para continuar.";
        else if (f.validity.tooLong) msg = `Use no máximo ${f.maxLength} caracteres.`;
        else msg = f.validationMessage || "Verifique esta resposta.";
      }
      messages.push(msg);
    }
  }
  const boxes = page.querySelectorAll('input[type="checkbox"]');
  if (boxes.length && page.dataset) {
    const checked = page.querySelectorAll('input[type="checkbox"]:checked').length;
    const min = Number(page.dataset.min || 0), max = Number(page.dataset.max || Infinity);
    if (checked < min) { messages.push(min === 1 ? "Marque pelo menos uma opção." : `Marque pelo menos ${min} opções.`); first ??= boxes[0]; }
    if (checked > max) { messages.push(`Marque no máximo ${max} opções.`); first ??= boxes[0]; }
  }
  const err = page.querySelector(".jf-error");
  if (err) { err.hidden = messages.length === 0; err.textContent = messages[0] || ""; }
  fieldsOf(page).forEach(f => f.toggleAttribute("aria-invalid", messages.length > 0 && f === first));
  return { ok: messages.length === 0, messages, first };
}

export function readAnswers(form) {
  const numeric = new Set(fieldsOf(form).filter(f => f.type === "range" || f.type === "number").map(f => f.name));
  return collectAnswers([...new FormData(form)].filter(([, v]) => typeof v === "string"), numeric);
}

export function multiNames(form) {
  return new Set([...form.querySelectorAll('input[type="checkbox"]')].map(f => f.name));
}

export function restoreAnswers(form, respostas) {
  for (const f of fieldsOf(form)) {
    if (!(f.name in respostas)) continue;
    const v = respostas[f.name];
    const list = (Array.isArray(v) ? v : [v]).map(String);
    if (f.type === "radio" || f.type === "checkbox") f.checked = list.includes(f.value);
    else if (f.tagName === "SELECT" && f.multiple) [...f.options].forEach(o => { o.selected = list.includes(o.value); });
    else f.value = list[0];
    f.dispatchEvent(new Event("input"));
  }
}

export function hasWeights(form) {
  return Boolean(form.querySelector("[data-pesos]"));
}

/** Pesos das opções marcadas; em escalas, peso × posição escolhida (0 a 1). */
export function weightContributions(form) {
  const out = [];
  form.querySelectorAll('input[type="radio"]:checked, input[type="checkbox"]:checked, option:checked')
    .forEach(el => { if (el.dataset.pesos) out.push(parseWeights(el.dataset.pesos)); });
  form.querySelectorAll('input[type="range"][data-pesos], input[type="number"][data-pesos]').forEach(el => {
    const min = Number(el.min || 0), max = Number(el.max || 1);
    const t = max > min ? (Number(el.value) - min) / (max - min) : 0;
    const w = parseWeights(el.dataset.pesos);
    out.push(Object.fromEntries(Object.entries(w).map(([k, v]) => [k, v * t])));
  });
  return out;
}
