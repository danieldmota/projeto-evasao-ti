/* Seletor de tema: Automático (segue o sistema) | Claro | Escuro.
   Carregado no <head> (sem defer) para aplicar o tema salvo antes da primeira pintura.
   A preferência fica em localStorage; se o armazenamento estiver indisponível
   (janela anônima, bloqueio), a página funciona no modo automático. */
(function () {
  "use strict";
  var KEY = "evasao-ti:tema";

  function read() {
    try { return localStorage.getItem(KEY) || "auto"; } catch (e) { return "auto"; }
  }
  function write(value) {
    try {
      if (value === "auto") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, value);
    } catch (e) { /* sem persistência: segue só nesta visita */ }
  }
  function apply(value) {
    var root = document.documentElement;
    if (value === "light" || value === "dark") root.setAttribute("data-theme", value);
    else root.removeAttribute("data-theme");
  }

  apply(read());

  document.addEventListener("DOMContentLoaded", function () {
    var buttons = document.querySelectorAll("[data-theme-set]");
    function sync(current) {
      buttons.forEach(function (b) {
        b.setAttribute("aria-pressed", String(b.getAttribute("data-theme-set") === current));
      });
    }
    sync(read());
    buttons.forEach(function (b) {
      b.addEventListener("click", function () {
        var value = b.getAttribute("data-theme-set");
        write(value);
        apply(value);
        sync(value);
      });
    });
  });
})();
