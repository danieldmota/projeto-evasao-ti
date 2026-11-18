// Tema Auto / Claro / Escuro. Fica no <head> para aplicar antes de desenhar a página.
(function () {
  var CHAVE = "evasao-ti:tema";

  function ler() {
    try { return localStorage.getItem(CHAVE) || "auto"; } catch (e) { return "auto"; }
  }
  function aplicar(tema) {
    if (tema === "light" || tema === "dark") document.documentElement.setAttribute("data-theme", tema);
    else document.documentElement.removeAttribute("data-theme");
  }

  aplicar(ler());

  document.addEventListener("DOMContentLoaded", function () {
    var botoes = document.querySelectorAll("[data-theme-set]");
    function marcar(tema) {
      botoes.forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.themeSet === tema)); });
    }
    marcar(ler());
    botoes.forEach(function (b) {
      b.addEventListener("click", function () {
        var tema = b.dataset.themeSet;
        try {
          if (tema === "auto") localStorage.removeItem(CHAVE);
          else localStorage.setItem(CHAVE, tema);
        } catch (e) { /* sem localStorage: vale só nesta visita */ }
        aplicar(tema);
        marcar(tema);
      });
    });
  });
})();
