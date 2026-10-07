/* GESCOL – module Examens (CEP) : aperçu en direct de la carte scolaire du candidat,
   tableau de saisie de l'examen blanc (maîtrise et moyenne calculées en direct, ajout / suppression de lignes). */
(function () {
  "use strict";
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function dateFr(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || ''); return m ? m[3] + '/' + m[2] + '/' + m[1] : (iso || ''); }

  /* ================================================================ carte scolaire du candidat */
  function initCarte(form) {
    var recto = $('#ca-recto'), verso = $('#ca-verso');
    function val(n) { var el = form.elements[n]; return el ? el.value : ''; }
    function maj() {
      $$('[data-k]', recto.parentNode).forEach(function (el) {
        var k = el.dataset.k, v;
        if (k === 'dir_titre') v = val('directeur_titre') === 'Directrice' ? 'La Directrice' : 'Le Directeur';
        else if (k === 'date_naissance') v = dateFr(val(k));
        else if (k === 'nom') v = val(k).toUpperCase();
        else v = val(k);
        el.textContent = v;
      });
      var src = '/cachet.svg?taille=180&sup=' + encodeURIComponent(val('cachet_sup')) + '&inf=' + encodeURIComponent(val('cachet_inf')) +
        '&centre=' + encodeURIComponent(val('cachet_centre')) + '&couleur=' + encodeURIComponent(val('cachet_couleur'));
      ['#ca-cachet-img', '#ca-cachet-mini'].forEach(function (s) { var i = $(s); if (i && i.dataset.src !== src) { i.dataset.src = src; i.src = src; } });
    }
    var minuterie = null;
    form.addEventListener('input', function () { clearTimeout(minuterie); minuterie = setTimeout(maj, 120); });
    form.addEventListener('change', maj);
    // photo : aperçu + clic sur le cadre de l'aperçu = choisir un fichier
    var cadre = $('#ca-photo');
    function photo(src) { if (src) cadre.innerHTML = '<img alt="Photo" src="' + src + '">'; }
    var pin = $('#ca-photo-in');
    if (pin && pin.dataset.src) photo(pin.dataset.src);
    form.addEventListener('photo', function (e) { photo(e.detail); });
    cadre.addEventListener('click', function () { var f = $('#ca-photo-in input[type=file]'); if (f) f.click(); });
    // signatures : rafraîchir l'aperçu après Enregistrer / Effacer
    $$('.sig-pad', form).forEach(function (pad) {
      pad.addEventListener('click', function (e) {
        var a = e.target.dataset && e.target.dataset.a; if (a !== 'enregistrer' && a !== 'effacer') return;
        var img = pad.dataset.cle.indexOf('eleve:') === 0 ? $('#ca-sig-eleve') : $('#ca-sig-dir');
        setTimeout(function () { img.style.visibility = ''; img.src = img.src.split('?')[0] + '?t=' + Date.now(); }, 900);
      });
    });
    // Réinitialiser : données de l'inscription et de l'école
    $('#ca-reinit').addEventListener('click', function () {
      if (!window.confirm("Remettre dans le formulaire les données de l'inscription et de l'école ? (rien n'est enregistré tant que vous ne cliquez pas sur « Enregistrer »)")) return;
      window.GESCOL.appliquer(form, JSON.parse(form.dataset.defaut || '{}')); maj();
      window.GESCOL.toast('Données de l\'inscription rétablies. Cliquez sur « Enregistrer » pour les conserver.');
    });
    // Charger : valeurs enregistrées
    $('#ca-charger').addEventListener('click', function () {
      fetch(form.dataset.donnees, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (r) {
        if (r.ok) { window.GESCOL.appliquer(form, r.valeurs); maj(); window.GESCOL.toast('Valeurs enregistrées rechargées.'); }
      });
    });
    maj();
  }

  /* ================================================================ examen blanc : tableau de saisie */
  function initBlanc(table) {
    var nbMat = parseInt(table.dataset.nbMat, 10) || 0, seuil = parseInt(table.dataset.seuil, 10) || 0;
    function note(v) {
      v = (v || '').trim().replace(',', '.'); if (v === '') return null;
      var x = Number(v); return isNaN(x) || x < 0 || x > 20 ? NaN : x;
    }
    function fmt(x) { return x === null ? '' : (Math.round(x * 100) / 100).toString().replace('.', ','); }
    function calculer() {
      var moys = [];
      $$('tbody tr.cb-ligne', table).forEach(function (tr) {
        var vals = [], err = false;
        $$('input.cb-note', tr).forEach(function (i) {
          var n = note(i.value); i.classList.toggle('err', n !== null && isNaN(n));
          if (n !== null && !isNaN(n)) vals.push(n); else if (n !== null) err = true;
        });
        var total = vals.reduce(function (a, b) { return a + b; }, 0), ok = vals.filter(function (v) { return v >= 10; }).length;
        var moy = vals.length ? total / vals.length : null, dec = $('.cb-dec', tr);
        $('.cb-total', tr).textContent = vals.length ? fmt(total) : '';
        $('.cb-moy', tr).textContent = vals.length ? fmt(moy) : '';
        $('.cb-ok', tr).textContent = vals.length ? ok + '/' + nbMat : '';
        var supprime = tr.classList.contains('suppr');
        dec.textContent = !vals.length ? (err ? '?' : 'ABSENT') : (ok >= seuil ? 'MAÎTRISE' : 'NON MAÎTRISE');
        dec.className = 'cb-dec c ' + (!vals.length ? '' : (ok >= seuil ? 'ok' : 'ko'));
        tr.dataset.moy = moy === null || supprime || !$('input[name=nom]', tr).value.trim() ? '' : moy;
        if (tr.dataset.moy !== '') moys.push(moy);
      });
      moys.sort(function (a, b) { return b - a; });
      $$('tbody tr.cb-ligne', table).forEach(function (tr) {
        var r = tr.dataset.moy === '' ? null : moys.indexOf(Number(tr.dataset.moy)) + 1;
        $('.cb-rang', tr).textContent = r ? r + (r === 1 ? 'er' : 'e') : '—';
      });
      var n = $$('tbody tr.cb-ligne', table).filter(function (tr) { return !tr.classList.contains('suppr') && $('input[name=nom]', tr).value.trim(); }).length;
      $$('.cb-compteur').forEach(function (s) { s.textContent = n; });
    }
    table.addEventListener('input', calculer);
    table.addEventListener('click', function (e) {
      var b = e.target.closest('[data-suppr]'); if (!b) return;
      var tr = b.closest('tr'), cb = $('input[name=suppr]', tr);
      if (cb) { cb.checked = !cb.checked; tr.classList.toggle('suppr', cb.checked); b.textContent = cb.checked ? '↺' : '✕'; b.title = cb.checked ? 'Annuler la suppression' : 'Supprimer ce candidat'; }
      else tr.remove();
      calculer();
    });
    var modele = $('#cb-modele');
    var ajout = $('#cb-ajouter');
    if (ajout && modele) ajout.addEventListener('click', function () {
      var tr = modele.content.firstElementChild.cloneNode(true);
      $('tbody', table).appendChild(tr); $('input[name=table]', tr).focus(); calculer();
    });
    // Entrée = cellule suivante vers le bas (saisie rapide des notes)
    table.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' || !e.target.classList.contains('cb-note')) return;
      e.preventDefault();
      var td = e.target.closest('td'), tr = td.parentNode, idx = Array.prototype.indexOf.call(tr.children, td), next = tr.nextElementSibling;
      if (next && next.children[idx]) { var i = $('input', next.children[idx]); if (i) i.focus(); }
    });
    calculer();
  }

  document.addEventListener('DOMContentLoaded', function () {
    var f = $('#f-carte'); if (f) initCarte(f);
    var t = $('#cb-table'); if (t) initBlanc(t);
    // import Excel : envoi dès le choix du fichier
    $$('input[data-envoi-auto]').forEach(function (i) { i.addEventListener('change', function () { if (i.files.length) i.form.submit(); }); });
  });
})();
