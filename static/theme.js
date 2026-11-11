/* v2.4.3 — bascule clair / sombre / auto ; mémorisée sur l'appareil (localStorage, jamais bloquant). */
(function () {
  var ORDRE = ["auto", "light", "dark"], LIB = {auto: "Auto", light: "Clair", dark: "Sombre"};
  function lire() { try { return localStorage.getItem("gescol_theme") || "auto"; } catch (e) { return "auto"; } }
  function poser(t) { document.documentElement.setAttribute("data-theme", t); }
  function maj(b, t) { b.textContent = "◐ " + LIB[t]; b.setAttribute("aria-label", "Thème d'affichage : " + LIB[t] + " (toucher pour changer)"); }
  function init() {
    document.querySelectorAll("[data-theme-btn]").forEach(function (b) {
      maj(b, lire());
      b.addEventListener("click", function () {
        var t = ORDRE[(ORDRE.indexOf(lire()) + 1) % 3];
        try { localStorage.setItem("gescol_theme", t); } catch (e) { /* stockage indisponible : thème valable pour la page */ }
        poser(t);
        document.querySelectorAll("[data-theme-btn]").forEach(function (x) { maj(x, t); });
      });
    });
  }
  poser(lire());
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
