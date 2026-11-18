// Testes da lógica pura da jornada: `node --test tests/js`
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  STEPS, FINAL, initialState, sanitizeState, canEnter, furthestAllowed, resolveRoute,
  canContinue, nextStepId, prevStepId, stepStatus, collectAnswers, toSubmissionAnswers,
  parseWeights, scoreByWeights, progress,
} from "../../web/assets/jornada/core.js";

const AREAS = [
  { code: "TI", label: "TI" },
  { code: "EXATAS_EXCETO_TI", label: "Exatas" },
  { code: "NATUREZA_SAUDE", label: "Saúde" },
];

const withResult = (extra = {}) => ({
  ...initialState(), iniciado: true, formularioConcluido: true,
  resultado: { affinities: [{ area_code: "TI", score: 1, rank: 1 }] }, ...extra,
});

test("oito etapas na ordem do site", () => {
  assert.deepEqual(STEPS.map(s => s.id),
    ["inicio", "formulario", "resultado", "interesse", "projeto", "dados", "competencias", "estudos"]);
});

test("estado inicial só permite o início", () => {
  const s = initialState();
  assert.equal(furthestAllowed(s), "inicio");
  assert.equal(resolveRoute("dados", s), "inicio");
  assert.equal(resolveRoute("rota-inexistente", s), "inicio");
});

test("não dá para pular o formulário nem o resultado", () => {
  const s = { ...initialState(), iniciado: true };
  assert.equal(resolveRoute("resultado", s), "formulario");
  assert.equal(canEnter("interesse", s), false);
});

test("etapas finais exigem decisão sobre o projeto", () => {
  const s = withResult({ interesse: "talvez" });
  assert.equal(resolveRoute("dados", s), "projeto");
  s.participacao = "recusada";
  assert.equal(resolveRoute("dados", s), "dados");
  assert.equal(furthestAllowed(s), "estudos");
});

test("fim só depois de concluir", () => {
  const s = withResult({ interesse: "sim", participacao: "demonstracao" });
  assert.equal(resolveRoute(FINAL, s), "estudos");
  s.concluido = true;
  assert.equal(resolveRoute(FINAL, s), FINAL);
});

test("canContinue bloqueia interesse e projeto sem escolha", () => {
  const s = withResult();
  assert.equal(canContinue("interesse", s), false);
  assert.equal(canContinue("projeto", s), false);
  assert.equal(canContinue("dados", s), true);
});

test("navegação anterior/próxima", () => {
  assert.equal(nextStepId("inicio"), "formulario");
  assert.equal(nextStepId("estudos"), FINAL);
  assert.equal(prevStepId("inicio"), null);
  assert.equal(prevStepId(FINAL), "estudos");
});

test("status visual das etapas", () => {
  const s = withResult({ interesse: "sim" });
  assert.equal(stepStatus("inicio", "interesse", s), "concluida");
  assert.equal(stepStatus("interesse", "interesse", s), "atual");
  assert.equal(stepStatus("projeto", "interesse", s), "disponivel");
  assert.equal(stepStatus("dados", "interesse", s), "bloqueada");
});

test("sanitizeState descarta lixo e nunca aceita dados pessoais", () => {
  const raw = {
    versao: 1, iniciado: true, nome: "Fulano", email: "a@b.c",
    interesse: "quem sabe", participacao: { name: "x" }, paginaFormulario: -3, respostas: [],
  };
  const s = sanitizeState(raw);
  assert.equal("nome" in s, false);
  assert.equal("email" in s, false);
  assert.equal(s.interesse, null);
  assert.equal(s.participacao, null);
  assert.equal(s.paginaFormulario, 0);
  assert.deepEqual(s.respostas, {});
  assert.deepEqual(sanitizeState(null), initialState());
  assert.deepEqual(sanitizeState({ versao: 99 }), initialState());
});

test("formulário só conta como concluído com resultado", () => {
  const s = sanitizeState({ versao: 1, formularioConcluido: true, resultado: null });
  assert.equal(s.formularioConcluido, false);
});

test("collectAnswers agrupa checkboxes e converte escalas", () => {
  const a = collectAnswers(
    [["atividades", "logica"], ["atividades", "criar_apps"], ["gosto", "4"], ["materia", "biologia"]],
    new Set(["gosto"]),
  );
  assert.deepEqual(a, { atividades: ["logica", "criar_apps"], gosto: 4, materia: "biologia" });
});

test("toSubmissionAnswers segue o contrato question_id/value", () => {
  const out = toSubmissionAnswers({ atividades: "logica", gosto: 4 }, new Set(["atividades"]));
  assert.deepEqual(out, [
    { question_id: "atividades", value: ["logica"] },
    { question_id: "gosto", value: 4 },
  ]);
});

test("parseWeights tolera espaços e ignora lixo", () => {
  assert.deepEqual(parseWeights("TI:2, EXATAS_EXCETO_TI: 1 ,x:y, :3"), { TI: 2, EXATAS_EXCETO_TI: 1 });
  assert.deepEqual(parseWeights(""), {});
});

test("scoreByWeights normaliza pela área líder e ordena", () => {
  const r = scoreByWeights([{ TI: 2 }, { TI: 1, NATUREZA_SAUDE: 1.5 }, { DESCONHECIDA: 9 }], AREAS);
  assert.deepEqual(r.map(x => x.area_code), ["TI", "NATUREZA_SAUDE", "EXATAS_EXCETO_TI"]);
  assert.equal(r[0].score, 1);
  assert.equal(r[1].score, 0.5);
  assert.equal(r[2].score, 0);
  assert.deepEqual(r.map(x => x.rank), [1, 2, 3]);
});

test("scoreByWeights sem respostas não divide por zero", () => {
  const r = scoreByWeights([], AREAS);
  assert.ok(r.every(x => x.score === 0));
});

test("progresso", () => {
  assert.deepEqual(progress("inicio"), { index: 0, total: 8, numero: 1, fracao: 0 });
  assert.equal(progress(FINAL).numero, 8);
});
