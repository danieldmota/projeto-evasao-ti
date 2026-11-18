/* Pontos de integração com o servidor. Cada adaptador funciona em dois modos:
   - configurado (endpoint definido em JORNADA_CONFIG): envia de verdade;
   - não configurado: modo demonstração, que NÃO envia nem guarda dados e avisa isso na tela.

   Contratos (ver src/evasao_ti/vocational/contracts.py):
   POST {api}/vocational/submissions  VocationalSubmission -> VocationalResult
   POST endpoints.interesse           ItInterestRecord
   POST endpoints.participacao        ProjectParticipation (único com dados pessoais) */

export const DISCLAIMER =
  "Este resultado é uma ferramenta de orientação para reflexão sobre interesses. " +
  "Não é um diagnóstico psicológico nem um teste validado.";

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error?.message || `HTTP ${res.status}`);
  return data;
}

export function createAdapters(cfg) {
  return {
    /** submission: VocationalSubmission; local(): afinidades pela pontuação provisória. */
    async pontuar(submission, local) {
      if (cfg.pontuacao === "api") {
        const r = await postJSON(`${cfg.api}/vocational/submissions`, submission);
        return { ...r, demonstracao: false };
      }
      const affinities = local();
      if (!affinities) throw new Error("o formulário não tem pesos (data-pesos); configure pontuacao: \"api\"");
      return {
        session_id: submission.session_id,
        questionnaire_version: submission.questionnaire_version,
        scoring_version: "pesos-html-provisorio",
        affinities,
        disclaimer: DISCLAIMER,
        demonstracao: true,
      };
    },

    async registrarInteresse(record) {
      if (!cfg.endpoints?.interesse) return { enviado: false };
      await postJSON(cfg.endpoints.interesse, record);
      return { enviado: true };
    },

    async participar(payload) {
      if (!cfg.endpoints?.participacao) return { status: "demonstracao" };
      await postJSON(cfg.endpoints.participacao, payload);
      return { status: "enviada" };
    },
  };
}
