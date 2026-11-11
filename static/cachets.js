/* v2.4.6 : bouton « Cachets » : masque les cachets (ronds et griffes) dans les PDF téléchargés ou imprimés.
   Le choix est mémorisé dans un cookie (sans_cachet=1) envoyé avec chaque téléchargement ; il vaut pour cet appareil. */
(function () {
  function lire() { return /(?:^|;\s*)sans_cachet=1/.test(document.cookie); }
  function ecrire(v) {
    document.cookie = "sans_cachet=" + (v ? "1" : "0") + "; path=/; max-age=" + (v ? 31536000 : 0) + "; SameSite=Lax";
  }
  function libelle(b) { b.textContent = lire() ? "✕ Cachets masqués" : "◉ Cachets affichés"; b.setAttribute("aria-pressed", lire() ? "true" : "false"); }
  function init() {
    var vus = document.querySelectorAll("[data-theme-btn]");
    for (var i = 0; i < vus.length; i++) {
      var ref = vus[i], b = document.createElement("button");
      b.type = "button"; b.className = "btn-theme"; b.setAttribute("data-cachet-btn", "");
      b.title = "Masquer ou afficher les cachets dans les PDF téléchargés";
      b.addEventListener("click", function () {
        ecrire(!lire());
        var tous = document.querySelectorAll("[data-cachet-btn]");
        for (var k = 0; k < tous.length; k++) libelle(tous[k]);
      });
      libelle(b);
      ref.parentNode.insertBefore(b, ref);
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
