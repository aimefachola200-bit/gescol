/* GESCOL – composants communs : signatures digitales, photo (fichier ou caméra),
   listes DDEMP → CS, sauvegarde/chargement des en-têtes de modules, tableaux cliquables. */
(function () {
  "use strict";
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function csrf() { var m = document.querySelector('meta[name=csrf]'); return m ? m.content : ''; }
  function json(url, data) {
    return fetch(url, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF': csrf() }, body: JSON.stringify(data) })
      .then(function (r) { return r.json().catch(function () { return { ok: r.ok }; }); });
  }
  window.GESCOL = { json: json };

  function toast(msg, ok) {
    var t = document.createElement('div');
    t.className = 'toast ' + (ok === false ? 'ko' : 'ok');
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add('vu'); }, 10);
    setTimeout(function () { t.remove(); }, 3200);
  }
  window.GESCOL.toast = toast;

  /* ---------------------------------------------------------------- signature digitale
     <div class="sig-pad" data-cle="ecole:1:directeur" data-titre="Signature du directeur" [data-champ="nom_input"]></div>
     Sans data-cle : l'image est placée dans un <input type=hidden name=data-champ>. */
  function initSignature(box) {
    if (box.dataset.pret) return; box.dataset.pret = 1;
    var cle = box.dataset.cle, champ = box.dataset.champ;
    box.innerHTML =
      '<div class="sig-titre">' + (box.dataset.titre || 'Signature') + '</div>' +
      '<canvas width="460" height="170" aria-label="Zone de signature : signez avec la souris ou le doigt"></canvas>' +
      '<div class="sig-actions">' +
      '<button type="button" class="btn sec petit" data-a="effacer">Effacer</button>' +
      '<button type="button" class="btn sec petit" data-a="apercu">Aperçu</button>' +
      (cle ? '<button type="button" class="btn petit" data-a="enregistrer">Enregistrer</button>' : '') +
      '<span class="sig-etat aide"></span></div>' +
      '<div class="sig-apercu" hidden><img alt="Aperçu de la signature"></div>' +
      (champ ? '<input type="hidden" name="' + champ + '">' : '');
    var cv = $('canvas', box), ctx = cv.getContext('2d'), etat = $('.sig-etat', box), vide = true, dessin = false, dernier = null;
    ctx.lineWidth = 2.4; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#0B2A6F';
    function pos(e) { var r = cv.getBoundingClientRect(); return { x: (e.clientX - r.left) * cv.width / r.width, y: (e.clientY - r.top) * cv.height / r.height }; }
    cv.addEventListener('pointerdown', function (e) { dessin = true; dernier = pos(e); cv.setPointerCapture(e.pointerId); e.preventDefault(); });
    cv.addEventListener('pointermove', function (e) {
      if (!dessin) return; var p = pos(e);
      ctx.beginPath(); ctx.moveTo(dernier.x, dernier.y); ctx.lineTo(p.x, p.y); ctx.stroke(); dernier = p; vide = false;
      etat.textContent = cle ? 'Non enregistrée' : '';
    });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (t) { cv.addEventListener(t, function () { if (dessin && champ) maj(); dessin = false; }); });
    function maj() { var i = $('input[name="' + champ + '"]', box); if (i) i.value = vide ? '' : cv.toDataURL('image/png'); }
    function charger(src) {
      var img = new Image();
      img.onload = function () { ctx.clearRect(0, 0, cv.width, cv.height); ctx.drawImage(img, 0, 0, cv.width, cv.height); vide = false; etat.textContent = 'Signature enregistrée'; if (champ) maj(); };
      img.src = src;
    }
    if (cle) {
      fetch('/signatures/' + cle + '.png?t=' + Date.now(), { credentials: 'same-origin' }).then(function (r) {
        if (r.ok) return r.blob();
      }).then(function (b) { if (b) charger(URL.createObjectURL(b)); else etat.textContent = 'Aucune signature enregistrée'; });
    } else if (box.dataset.valeur) { charger(box.dataset.valeur); }
    box.addEventListener('click', function (e) {
      var a = e.target.dataset && e.target.dataset.a; if (!a) return;
      if (a === 'effacer') {
        ctx.clearRect(0, 0, cv.width, cv.height); vide = true; if (champ) maj();
        $('.sig-apercu', box).hidden = true;
        if (cle) json('/signatures/' + cle, { effacer: 1 }).then(function () { etat.textContent = 'Signature effacée'; });
      } else if (a === 'apercu') {
        var ap = $('.sig-apercu', box); ap.hidden = !ap.hidden; $('img', ap).src = cv.toDataURL('image/png');
      } else if (a === 'enregistrer') {
        if (vide) { toast('Signez d\'abord dans le cadre.', false); return; }
        json('/signatures/' + cle, { image: cv.toDataURL('image/png') }).then(function (r) {
          etat.textContent = r.ok ? 'Signature enregistrée' : (r.erreur || 'Erreur');
          toast(r.ok ? 'Signature enregistrée.' : (r.erreur || 'Erreur'), !!r.ok);
        });
      }
    });
  }

  /* ---------------------------------------------------------------- photo : fichier ou caméra
     <div class="photo-capture" data-champ="photo_data" data-src="/url/photo.jpg"></div>
     Le formulaire reçoit une image JPEG en data URL dans le champ caché.
     Caméra : bouton « Basculer » (avant ↔ arrière, facingMode user / environment), liste des caméras disponibles
     (enumerateDevices) quand il y en a plusieurs, dernier choix mémorisé (localStorage gescol-camera-face / -id),
     repli automatique sur la caméra existante quand la face demandée manque (PC sans caméra arrière). */
  function initPhoto(box) {
    if (box.dataset.pret) return; box.dataset.pret = 1;
    var champ = box.dataset.champ || 'photo_data';
    box.innerHTML =
      '<div class="pc-cadre" title="Cliquer pour choisir une photo"><img alt="Photo" ' + (box.dataset.src ? 'src="' + box.dataset.src + '"' : 'hidden') + '>' +
      '<span class="pc-vide"' + (box.dataset.src ? ' hidden' : '') + '>Cliquer pour<br>ajouter la photo</span>' +
      '<video playsinline muted hidden></video></div>' +
      '<div class="pc-actions">' +
      '<label class="btn sec petit">Fichier<input type="file" accept="image/*" hidden></label>' +
      '<button type="button" class="btn sec petit" data-a="camera">Caméra</button>' +
      '<button type="button" class="btn petit" data-a="prendre" hidden>Prendre</button>' +
      '<button type="button" class="btn sec petit" data-a="basculer" hidden title="Caméra avant / arrière">⇄ Basculer</button>' +
      '<label class="btn sec petit pc-mobile" hidden>Appareil photo<input type="file" accept="image/*" capture="environment" hidden></label>' +
      '</div><select class="pc-cams" hidden aria-label="Choix de la caméra"></select>' +
      '<input type="hidden" name="' + champ + '">';
    var img = $('img', box), vid = $('video', box), vide = $('.pc-vide', box), sortie = $('input[name="' + champ + '"]', box), flux = null;
    /* Caméra avant ('user') ou arrière ('environment') + choix d'un appareil précis ; dernier choix mémorisé. */
    var basculer = $('[data-a=basculer]', box), selCams = $('.pc-cams', box), cameras = [];
    var face = 'user', appareil = '';
    try { face = localStorage.getItem('gescol-camera-face') || 'user'; appareil = localStorage.getItem('gescol-camera-id') || ''; } catch (_) {}
    function memoriser() { try { localStorage.setItem('gescol-camera-face', face); localStorage.setItem('gescol-camera-id', appareil); } catch (_) {} }
    function listerCameras() {
      if (!navigator.mediaDevices.enumerateDevices) return Promise.resolve([]);
      return navigator.mediaDevices.enumerateDevices().then(function (l) {
        cameras = l.filter(function (d) { return d.kind === 'videoinput'; });
        selCams.innerHTML = cameras.map(function (d, i) {
          return '<option value="' + d.deviceId + '">' + (d.label || ('Caméra ' + (i + 1))).replace(/</g, '&lt;') + '</option>';
        }).join('');
        selCams.hidden = !(flux && cameras.length > 1);
        return cameras;
      }).catch(function () { return []; });
    }
    function contraintes(mode) {
      // mode 1 : appareil mémorisé ; 2 : face demandée ; 3 : face opposée ; 4 : n'importe quelle caméra
      if (mode === 1) return { deviceId: { exact: appareil }, width: { ideal: 1280 } };
      if (mode === 2) return { facingMode: face, width: { ideal: 1280 } };
      if (mode === 3) return { facingMode: face === 'user' ? 'environment' : 'user', width: { ideal: 1280 } };
      return true;
    }
    function poser(url) {
      var i = new Image();
      i.onload = function () {
        var c = document.createElement('canvas'), W = 360, H = 450, r = Math.max(W / i.width, H / i.height);
        c.width = W; c.height = H;
        c.getContext('2d').drawImage(i, (W - i.width * r) / 2, (H - i.height * r) / 2, i.width * r, i.height * r);
        var d = c.toDataURL('image/jpeg', 0.85);
        img.src = d; img.hidden = false; vide.hidden = true; sortie.value = d;
        box.dispatchEvent(new CustomEvent('photo', { detail: d, bubbles: true }));
      };
      i.src = url;
    }
    $$('input[type=file]', box).forEach(function (f) {
      f.addEventListener('change', function () { if (f.files[0]) poser(URL.createObjectURL(f.files[0])); });
    });
    $('.pc-cadre', box).addEventListener('click', function () { if (!flux) $('input[type=file]', box).click(); });
    var cam = $('[data-a=camera]', box), prendre = $('[data-a=prendre]', box);
    if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) || !window.isSecureContext) {
      cam.hidden = true; $('.pc-mobile', box).hidden = false;  // http sur le réseau local : appareil photo natif
    }
    function couper() { if (flux) { flux.getTracks().forEach(function (t) { t.stop(); }); flux = null; } }
    function arreter() {
      couper(); vid.hidden = true; prendre.hidden = true; basculer.hidden = true; selCams.hidden = true; cam.textContent = 'Caméra';
      if (!sortie.value && !box.dataset.src) { vide.hidden = false; } else { img.hidden = false; }
    }
    function demarrer(mode) {
      mode = mode || (appareil ? 1 : 2);
      couper();   // l'ancien flux est arrêté avant d'en demander un autre (une seule caméra à la fois)
      return navigator.mediaDevices.getUserMedia({ video: contraintes(mode), audio: false }).then(function (s) {
        flux = s; vid.srcObject = s; vid.hidden = false; img.hidden = true; vide.hidden = true; prendre.hidden = false; cam.textContent = 'Annuler'; vid.play();
        var piste = s.getVideoTracks()[0], reg = piste && piste.getSettings ? piste.getSettings() : {};
        if (reg.facingMode === 'user' || reg.facingMode === 'environment') face = reg.facingMode;
        if (mode === 3) { toast('Caméra ' + (face === 'user' ? 'arrière' : 'avant') + ' introuvable : caméra ' + (face === 'user' ? 'avant' : 'arrière') + ' utilisée.'); }
        if (mode === 4) { face = 'user'; }
        if (reg.deviceId) appareil = reg.deviceId;
        memoriser();
        return listerCameras().then(function (l) {
          basculer.hidden = l.length === 1;   // une seule caméra (PC) : rien à basculer
          if (reg.deviceId) selCams.value = reg.deviceId;
        });
      }).catch(function (e) {
        var refus = e && (e.name === 'NotAllowedError' || e.name === 'SecurityError');
        if (mode === 1 && !refus) return demarrer(2);          // l'appareil mémorisé n'existe plus
        if (mode === 2 && !refus) return demarrer(3);   // la face demandée n'existe pas (PC sans caméra arrière)
        if (mode === 3 && !refus) return demarrer(4);
        arreter();
        toast(refus ? 'Caméra refusée : autorisez-la dans le navigateur ou utilisez « Fichier ».'
          : 'Caméra inaccessible : autorisez-la dans le navigateur ou utilisez « Fichier ».', false);
        $('.pc-mobile', box).hidden = false;
      });
    }
    cam.addEventListener('click', function () {
      if (flux) { arreter(); return; }
      demarrer();
    });
    basculer.addEventListener('click', function () {
      if (!flux) return;
      face = face === 'user' ? 'environment' : 'user';
      // avec plusieurs appareils connus mais sans facingMode (PC à deux webcams) : passer à l'appareil suivant
      var actuel = cameras.map(function (d) { return d.deviceId; }).indexOf(appareil);
      var piste = flux.getVideoTracks()[0], reg = piste && piste.getSettings ? piste.getSettings() : {};
      if (cameras.length > 1 && !reg.facingMode && actuel >= 0) { appareil = cameras[(actuel + 1) % cameras.length].deviceId; demarrer(1); return; }
      appareil = ''; demarrer(2);
    });
    selCams.addEventListener('change', function () { appareil = selCams.value; if (flux) demarrer(1); });
    prendre.addEventListener('click', function () {
      var c = document.createElement('canvas'); c.width = vid.videoWidth; c.height = vid.videoHeight;
      c.getContext('2d').drawImage(vid, 0, 0); arreter(); poser(c.toDataURL('image/jpeg', 0.9));
    });
  }

  /* ---------------------------------------------------------------- DDEMP → CS
     <select data-dep> (ou input list) et <input data-cs list="..."> dans le même formulaire */
  function initCascade(form) {
    var dep = $('[data-dep]', form), cs = $('[data-cs]', form);
    if (!dep || !cs || !window.CS_PAR_DEP) return;
    var dl = document.createElement('datalist'); dl.id = 'dl-cs-' + Math.random().toString(36).slice(2);
    form.appendChild(dl); cs.setAttribute('list', dl.id);
    function remplir() {
      var l = window.CS_PAR_DEP[dep.value] || [].concat.apply([], Object.keys(window.CS_PAR_DEP).map(function (k) { return window.CS_PAR_DEP[k]; }));
      dl.innerHTML = l.map(function (c) { return '<option value="' + c.replace(/"/g, '&quot;') + '">'; }).join('');
      var n = $('.nb-cs', form); if (n) n.textContent = (window.CS_PAR_DEP[dep.value] || []).length ? (window.CS_PAR_DEP[dep.value].length + ' circonscriptions') : '';
    }
    dep.addEventListener('change', function () { remplir(); if (cs.value && (window.CS_PAR_DEP[dep.value] || []).indexOf(cs.value) < 0) cs.value = ''; });
    remplir();
  }

  /* ---------------------------------------------------------------- en-têtes de modules : Sauvegarder / Charger / Réinitialiser
     <form data-doc="cle"> … <button data-doc-action="sauver|charger|reinit"> */
  function valeurs(form) {
    var o = {};
    $$('input,select,textarea', form).forEach(function (el) {
      if (!el.name || el.type === 'file' || el.type === 'password' || el.dataset.nosave !== undefined) return;
      if (el.type === 'checkbox') { if (!(el.name in o)) o[el.name] = []; if (el.checked) o[el.name].push(el.value); }
      else if (el.type === 'radio') { if (el.checked) o[el.name] = el.value; }
      else o[el.name] = el.value;
    });
    return o;
  }
  function appliquer(form, o) {
    $$('input,select,textarea', form).forEach(function (el) {
      if (!el.name || !(el.name in o) || el.type === 'file') return;
      var v = o[el.name];
      if (el.type === 'checkbox') el.checked = Array.isArray(v) ? v.indexOf(el.value) >= 0 : !!v;
      else if (el.type === 'radio') el.checked = el.value === v;
      else el.value = v;
      el.dispatchEvent(new Event('change', { bubbles: true }));
    });
  }
  window.GESCOL.valeurs = valeurs; window.GESCOL.appliquer = appliquer;
  function initDoc(form) {
    var cle = form.dataset.doc;
    form.addEventListener('click', function (e) {
      var a = e.target.dataset && e.target.dataset.docAction; if (!a) return;
      e.preventDefault();
      if (a === 'sauver') {
        json('/documents-modules/' + encodeURIComponent(cle), valeurs(form)).then(function (r) { toast(r.ok ? 'Enregistré.' : (r.erreur || 'Erreur'), !!r.ok); });
      } else if (a === 'charger') {
        fetch('/documents-modules/' + encodeURIComponent(cle), { credentials: 'same-origin' }).then(function (r) { return r.json(); })
          .then(function (r) { if (r.donnees) { appliquer(form, r.donnees); toast('Données chargées (enregistrées le ' + r.maj + ').'); } else toast('Rien d\'enregistré pour le moment.', false); });
      } else if (a === 'reinit') {
        if (!window.confirm('Vider le formulaire ? (les données déjà enregistrées ne sont pas supprimées)')) return;
        $$('input,select,textarea', form).forEach(function (el) {
          if (el.type === 'hidden' || el.type === 'submit' || el.type === 'button' || el.dataset.garder !== undefined) return;
          if (el.type === 'checkbox' || el.type === 'radio') el.checked = false; else el.value = '';
        });
        form.dispatchEvent(new Event('reinit'));
      }
    });
  }

  /* ---------------------------------------------------------------- confirmation des boutons dangereux */
  document.addEventListener('submit', function (e) {
    var b = e.submitter, msg = (b && b.dataset.confirmer) || e.target.dataset.confirmer;
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  /* ---------------------------------------------------------------- tout cocher / tout décocher + compteur
     <div data-coches> … <button data-cocher="1|0"> … <span class="nb-coches"> */
  function initCoches(z) {
    function compter() { var n = $$('input[type=checkbox]:checked', z).filter(function (c) { return !c.dataset.cocher; }).length; $$('.nb-coches', z).forEach(function (s) { s.textContent = n; }); z.dispatchEvent(new Event('coches')); }
    z.addEventListener('click', function (e) {
      var v = e.target.dataset && e.target.dataset.cocher; if (v === undefined) return;
      e.preventDefault(); $$('input[type=checkbox]', z).forEach(function (c) { c.checked = v === '1'; }); compter();
    });
    z.addEventListener('change', compter); compter();
  }

  /* ---------------------------------------------------------------- menu latéral (téléphone) */
  function initMenu() {
    var b = $('#btn-menu'), side = $('#lateral'), voile = $('#voile');
    if (!b || !side) return;
    function basculer(o) { side.classList.toggle('ouvert', o); voile.hidden = !o; b.setAttribute('aria-expanded', o); }
    b.addEventListener('click', function () { basculer(!side.classList.contains('ouvert')); });
    voile.addEventListener('click', function () { basculer(false); });
    var actif = $('#lateral a.actif'); if (actif && actif.scrollIntoView) actif.scrollIntoView({ block: 'center' });
    try {  // groupes ouverts/fermés mémorisés
      var m = JSON.parse(localStorage.getItem('gescol-menu') || '{}');
      $$('#lateral details[data-g]').forEach(function (d) {
        if (m[d.dataset.g] !== undefined && !d.classList.contains('actif')) d.open = m[d.dataset.g];
        d.addEventListener('toggle', function () { m[d.dataset.g] = d.open; try { localStorage.setItem('gescol-menu', JSON.stringify(m)); } catch (_) {} });
      });
    } catch (_) {}
  }

  function init(racine) {
    $$('.sig-pad', racine).forEach(initSignature);
    $$('.photo-capture', racine).forEach(initPhoto);
    $$('form', racine).forEach(initCascade);
    $$('form[data-doc]', racine).forEach(initDoc);
    $$('[data-coches]', racine).forEach(initCoches);
    $$('input[type=password]', racine).forEach(initOeil);
  }

  // Œil pour afficher / masquer un mot de passe (saisie sur téléphone)
  function initOeil(inp) {
    if (inp.dataset.oeil) return;
    inp.dataset.oeil = '1';
    var cadre = document.createElement('span');
    cadre.className = 'mdp-cadre';
    inp.parentNode.insertBefore(cadre, inp);
    cadre.appendChild(inp);
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'mdp-oeil'; b.title = 'Afficher le mot de passe';
    b.setAttribute('aria-label', 'Afficher ou masquer le mot de passe');
    b.innerHTML = '&#128065;';
    b.addEventListener('click', function () {
      var vis = inp.type === 'password';
      inp.type = vis ? 'text' : 'password';
      b.classList.toggle('actif', vis);
      b.title = vis ? 'Masquer le mot de passe' : 'Afficher le mot de passe';
      inp.focus();
    });
    cadre.appendChild(b);
  }
  window.GESCOL.init = init;
  document.addEventListener('DOMContentLoaded', function () { init(document); initMenu(); });
})();
