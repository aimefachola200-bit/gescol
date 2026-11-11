/* SCOLARIS – composants communs : signatures digitales, photo (fichier ou caméra),
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
  window.SCOLARIS = { json: json };

  function toast(msg, ok) {
    var t = document.createElement('div');
    t.className = 'toast ' + (ok === false ? 'ko' : 'ok');
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add('vu'); }, 10);
    setTimeout(function () { t.remove(); }, 3200);
  }
  window.SCOLARIS.toast = toast;

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
     Caméra : bouton « Basculer » (avant / arrière, facingMode user / environment), liste des caméras disponibles
     (enumerateDevices) quand il y en a plusieurs, dernier choix mémorisé (localStorage scolaris-camera-face / -id),
     repli automatique sur la caméra existante quand la face demandée manque (PC sans caméra arrière). */
  /* v1.10.10 — caméra avant / arrière : appareil de la face voulue d'après son nom (front / back, avant / arrière…),
     sinon l'appareil suivant de la liste ; null s'il n'y a qu'une caméra. */
  function choisirCamera(cams, face, actuel) {
    if (!cams || cams.length < 2) return null;
    var re = face === 'user' ? /front|avant|user|selfie|facing front/i : /back|arri[eè]re|rear|environment|facing back/i;
    var parNom = cams.filter(function (c) { return re.test(c.label || ''); });
    var autre = parNom.filter(function (c) { return c.deviceId !== actuel; })[0] || parNom[0];
    if (autre) return autre.deviceId;
    var i = cams.map(function (c) { return c.deviceId; }).indexOf(actuel);
    return cams[(i + 1) % cams.length].deviceId;
  }
  window.SCOLARIS_choisirCamera = choisirCamera;

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
    try { face = localStorage.getItem('scolaris-camera-face') || 'user'; appareil = localStorage.getItem('scolaris-camera-id') || ''; } catch (_) {}
    function memoriser() { try { localStorage.setItem('scolaris-camera-face', face); localStorage.setItem('scolaris-camera-id', appareil); } catch (_) {} }
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
      if (mode === 2) return { facingMode: { exact: face }, width: { ideal: 1280 } };   // v1.10.10 : face imposée
      if (mode === 5) return { facingMode: { ideal: face }, width: { ideal: 1280 } };
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
        if (mode === 2 && !refus) return demarrer(5);   // « exact » refusé par certains appareils : face préférée
        if (mode === 5 && !refus) return demarrer(3);   // la face demandée n'existe pas (PC sans caméra arrière)
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
      // v1.10.10 : on choisit l'APPAREIL (avant / arrière d'après son nom, sinon le suivant) : certains téléphones
      // ignorent « facingMode » et rouvraient toujours la même caméra.
      var autre = choisirCamera(cameras, face, appareil);
      if (autre) { appareil = autre; demarrer(1); return; }
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

  /* ---------------------------------------------------------------- département → commune → arrondissement → village
     Champs repérés par data-geo="departement|commune|arrondissement|village|lieu" dans un même formulaire.
     Référentiel : /static/referentiel_villages.json (12 départements, 77 communes, 546 arrondissements,
     5 290 villages et quartiers de ville), chargé une seule fois et seulement si la page en a besoin. */
  var geoPromesse = null;
  function geoCharger() {
    if (!geoPromesse) {
      var base = (document.querySelector('script[src*="scolaris.js"]') || {}).src || '/static/scolaris.js';
      geoPromesse = fetch(base.replace(/scolaris\.js.*$/, 'referentiel_villages.json'), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); }).then(function (j) {
          var idx = { deps: [], communes: [], arr: {}, vil: {}, lieux: [] };
          j.d.forEach(function (d) {
            idx.deps.push(d[0]);
            d[1].forEach(function (c) {
              idx.communes.push({ nom: c[0], dep: d[0] });
              c[1].forEach(function (a) {
                (idx.arr[c[0]] = idx.arr[c[0]] || []).push(a[0]);
                a[1].forEach(function (v) {
                  var o = { nom: v, arr: a[0], com: c[0], dep: d[0] };
                  (idx.vil[c[0]] = idx.vil[c[0]] || []).push(o);
                  idx.lieux.push(o);
                });
              });
            });
          });
          return idx;
        });
    }
    return geoPromesse;
  }
  function geoCle(s) {
    return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/^(DDEMP|DEPARTEMENT|COMMUNE)\s+(DE L'|DE LA|DU|DES|DE|D')?\s*/, '').replace(/[^A-Z0-9]/g, '');
  }
  function initGeo(form) {
    var ch = {};
    $$('[data-geo]', form).forEach(function (el) { ch[el.dataset.geo] = ch[el.dataset.geo] || []; ch[el.dataset.geo].push(el); });
    if (!Object.keys(ch).length) return;
    var un = function (k) { return (ch[k] || [])[0]; };
    function liste(el, options) {
      var dl = el._geoDl;
      if (!dl) {
        dl = document.createElement('datalist'); dl.id = 'dl-geo-' + Math.random().toString(36).slice(2);
        form.appendChild(dl); el.setAttribute('list', dl.id); el.setAttribute('autocomplete', 'off'); el._geoDl = dl;
      }
      dl.innerHTML = options.map(function (o) {
        return '<option value="' + o[0].replace(/"/g, '&quot;') + '"' + (o[1] ? ' label="' + o[1].replace(/"/g, '&quot;') + '"' : '') + '>';
      }).join('');
    }
    geoCharger().then(function (G) {
      function depChoisi() {
        var d = un('departement'); if (!d || !d.value) return null;
        var k = geoCle(d.value); return G.deps.filter(function (x) { return geoCle(x) === k || k.indexOf(geoCle(x)) >= 0; })[0] || null;
      }
      function communeDe(v) { var k = geoCle(v); return G.communes.filter(function (c) { return geoCle(c.nom) === k; })[0] || null; }
      function majCommunes() {
        var dep = depChoisi();
        (ch.commune || []).forEach(function (el) {
          liste(el, G.communes.filter(function (c) { return !dep || c.dep === dep; })
            .map(function (c) { return [c.nom, dep ? '' : c.nom + ' (' + c.dep + ')']; }));
        });
        majArr();
      }
      function majArr() {
        var c = un('commune') && communeDe(un('commune').value);
        (ch.arrondissement || []).forEach(function (el) { liste(el, c ? (G.arr[c.nom] || []).map(function (a) { return [a, '']; }) : []); });
        majVillages();
      }
      function majVillages() {
        var c = un('commune') && communeDe(un('commune').value), a = un('arrondissement') && un('arrondissement').value;
        var lst = c ? (G.vil[c.nom] || []) : (un('commune') ? [] : G.lieux);
        if (a) { var ka = geoCle(a), f = lst.filter(function (v) { return geoCle(v.arr) === ka; }); if (f.length) lst = f; }
        (ch.village || []).forEach(function (el) { liste(el, lst.map(function (v) { return [v.nom, v.nom + ' – ' + v.arr + (c ? '' : ', ' + v.com)]; })); });
      }
      // lieu libre (lieu de naissance, résidence…) : communes et villages, « Village (Commune) »
      (ch.lieu || []).forEach(function (el) {
        liste(el, G.communes.map(function (c) { return [c.nom, 'Commune – ' + c.dep]; })
          .concat(G.lieux.map(function (v) { return [v.nom + ' (' + v.com + ')', v.arr + ', ' + v.com]; })));
      });
      (ch.departement || []).forEach(function (el) {
        if (!el.hasAttribute('data-dep') && el.tagName === 'INPUT') liste(el, G.deps.map(function (d) { return [d, '']; }));
        el.addEventListener('change', majCommunes);
      });
      // remplir automatiquement les niveaux supérieurs quand on choisit plus bas
      function poser(k, v) { (ch[k] || []).forEach(function (el) { if (el.value !== v) { el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); } }); }
      (ch.commune || []).forEach(function (el) {
        el.addEventListener('change', function () {
          var c = communeDe(el.value); if (!c) { majArr(); return; }
          if (el.value !== c.nom) el.value = c.nom;
          var d = un('departement');
          if (d && d.tagName === 'INPUT' && !d.hasAttribute('data-dep') && geoCle(d.value) !== geoCle(c.dep)) poser('departement', c.dep);
          majArr();
        });
      });
      (ch.arrondissement || []).forEach(function (el) { el.addEventListener('change', majVillages); });
      (ch.village || []).forEach(function (el) {
        el.addEventListener('change', function () {
          var k = geoCle(el.value), c = un('commune') && communeDe(un('commune').value);
          var v = (c ? (G.vil[c.nom] || []) : G.lieux).filter(function (x) { return geoCle(x.nom) === k; })[0];
          if (!v) return;
          if (un('arrondissement') && !un('arrondissement').value) poser('arrondissement', v.arr);
          if (un('commune') && !un('commune').value) poser('commune', v.com);
        });
      });
      majCommunes();
    }).catch(function () {});
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
  window.SCOLARIS.valeurs = valeurs; window.SCOLARIS.appliquer = appliquer;
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

  /* ---------------------------------------------------------------- v1.8 : saisie hors ligne
     <form method="post" data-hors-ligne="Appel du CM2 A"> : si le serveur ne répond pas (Wi-Fi coupé, PC éteint),
     la saisie est gardée sur l'appareil (localStorage) puis renvoyée automatiquement dès le retour du réseau
     (événement « online » et nouvel essai toutes les 30 s). Le badge « saisies en attente » de la barre du haut
     indique le nombre de saisies gardées. */
  var CLE_FILE = 'scolaris-file-attente';
  function fileLire() { try { return JSON.parse(localStorage.getItem(CLE_FILE) || '[]'); } catch (_) { return []; } }
  function fileEcrire(l) { try { localStorage.setItem(CLE_FILE, JSON.stringify(l)); } catch (_) {} majFile(); }
  function majFile() {
    var b = $('#file-attente'); if (!b) return;
    var n = fileLire().length; b.hidden = !n; var t = $('.fa-n', b); if (t) t.textContent = n;
  }
  function posterCorps(action, corps) {
    return fetch(action, { method: 'POST', credentials: 'same-origin', redirect: 'follow',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: corps }).then(function (r) {
      if (r.status >= 500 || r.status === 0) throw new Error('serveur');
      if (/\/login(\?|$)/.test(r.url || '')) throw new Error('connexion');   // session expirée : on garde la saisie
      return r;
    });
  }
  var envoiEnCours = false;
  function viderFile() {
    if (envoiEnCours) return;
    var l = fileLire(); if (!l.length) return;
    envoiEnCours = true;
    var it = l[0];
    posterCorps(it.action, it.corps).then(function () {
      fileEcrire(fileLire().filter(function (x) { return x.id !== it.id; }));
      toast((it.titre || 'Saisie') + ' : envoyée au serveur.', true);
      envoiEnCours = false; viderFile();
    }).catch(function () { envoiEnCours = false; });
  }
  window.SCOLARIS.viderFile = viderFile;
  function initHorsLigne(form) {
    if (form.dataset.hlPret) return; form.dataset.hlPret = 1;
    form.addEventListener('submit', function (e) {
      var b = e.submitter;
      if (e.defaultPrevented || (b && b.dataset.confirmer) || form.dataset.confirmer || form.enctype === 'multipart/form-data') return;
      e.preventDefault();
      var fd = new FormData(form);
      if (b && b.name) fd.append(b.name, b.value);
      var corps = new URLSearchParams(fd).toString(), action = form.getAttribute('action') || location.pathname + location.search;
      if (b) b.disabled = true;
      posterCorps(action, corps).then(function (r) { location.href = r.url || location.href; }).catch(function (err) {
        var l = fileLire();
        l.push({ id: Date.now() + '-' + Math.random().toString(36).slice(2), action: action, corps: corps,
                 titre: form.dataset.horsLigne || document.title, quand: new Date().toISOString() });
        fileEcrire(l);
        if (b) b.disabled = false;
        // les pages qui retirent les noms des champs avant l'envoi (grille des notes) les retrouvent
        $$('[data-nom]', form).forEach(function (el) { if (!el.name) el.name = el.dataset.nom; });
        toast(err && err.message === 'connexion'
          ? 'Session expirée : saisie gardée sur l\'appareil. Reconnectez-vous, elle sera envoyée automatiquement.'
          : 'Pas de connexion au serveur : saisie gardée sur cet appareil, envoi automatique dès le retour du réseau.', true);
      });
    });
  }
  window.addEventListener('online', viderFile);
  setInterval(viderFile, 30000);

  /* ---------------------------------------------------------------- v1.8 : nouvelle version disponible
     <div id="bandeau-maj" data-depot="compte/depot" data-version="1.8.0" data-fichier="NOM.apk|NOM.exe"> : une fois
     par 12 h, la dernière version publiée sur GitHub est comparée à la version installée. */
  function versionNum(v) { return String(v || '').replace(/^v/i, '').split('.').map(function (x) { return parseInt(x, 10) || 0; }); }
  function plusRecente(a, b) {
    var x = versionNum(a), y = versionNum(b);
    for (var i = 0; i < Math.max(x.length, y.length); i++) { if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); }
    return false;
  }
  function initMaj() {
    var b = $('#bandeau-maj'); if (!b || !window.fetch) return;
    var depot = b.dataset.depot, actuelle = b.dataset.version, cache = {};
    try { cache = JSON.parse(localStorage.getItem('scolaris-maj') || '{}'); } catch (_) {}
    function afficher(tag) {
      if (!tag || !plusRecente(tag, actuelle)) return;
      try { if (localStorage.getItem('scolaris-maj-ignore') === tag) return; } catch (_) {}
      var f = b.dataset.fichier, lien = 'https://github.com/' + depot + '/releases/' + (f ? 'latest/download/' + f : 'latest');
      $('.maj-v', b).textContent = tag.replace(/^v/i, '');
      $('.maj-lien', b).href = lien;
      b.hidden = false;
      $('.maj-plus-tard', b).addEventListener('click', function () { b.hidden = true; try { localStorage.setItem('scolaris-maj-ignore', tag); } catch (_) {} });
    }
    if (cache.tag && cache.quand && Date.now() - cache.quand < 12 * 3600 * 1000) { afficher(cache.tag); return; }
    fetch('https://api.github.com/repos/' + depot + '/releases/latest', { headers: { Accept: 'application/vnd.github+json' } })
      .then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
        if (!j || !j.tag_name) return;
        try { localStorage.setItem('scolaris-maj', JSON.stringify({ tag: j.tag_name, quand: Date.now() })); } catch (_) {}
        afficher(j.tag_name);
      }).catch(function () {});
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
      var m = JSON.parse(localStorage.getItem('scolaris-menu') || '{}');
      $$('#lateral details[data-g]').forEach(function (d) {
        if (m[d.dataset.g] !== undefined && !d.classList.contains('actif')) d.open = m[d.dataset.g];
        d.addEventListener('toggle', function () { m[d.dataset.g] = d.open; try { localStorage.setItem('scolaris-menu', JSON.stringify(m)); } catch (_) {} });
      });
    } catch (_) {}
  }


  /* ---------------------------------------------------------------- en-têtes fixes (v1.17)
     Chaque tableau garde sa ligne de rubriques (thead, ou premières lignes faites de <th>) visible pendant le
     défilement ; les lignes d'en-tête successives s'empilent. Dans un cadre .tw, l'en-tête se colle en haut du
     cadre et la 1re colonne à gauche quand le tableau déborde ; hors cadre, sous la barre du haut.
     data-entete="non" sur un tableau (ou un parent) : pas d'en-tête fixe. */
  function barresHaut() {
    var h = 0;
    $$('.barre-haut, header.top, .barre-doc, .indicateurs').forEach(function (b) {
      var cs = getComputedStyle(b);
      if ((cs.position === 'sticky' || cs.position === 'fixed') && b.offsetHeight && cs.display !== 'none')
        h = Math.max(h, (parseFloat(cs.top) || 0) + b.offsetHeight);
    });
    return h;
  }
  function lignesEntete(t) {
    var rows = t.tHead ? Array.prototype.slice.call(t.tHead.rows) : [];
    if (!rows.length) {
      for (var i = 0; i < t.rows.length && i < 4; i++) {
        var r = t.rows[i], cells = Array.prototype.slice.call(r.cells);
        if (cells.length && cells.every(function (c) { return c.tagName === 'TH'; })) rows.push(r); else break;
      }
    }
    return rows;
  }
  function fixerTableau(t) {
    if (t.closest('[data-entete="non"]') || t.closest('.sig-pad')) return;
    var rows = lignesEntete(t);
    var cadre = t.closest('.tw');
    var y = 0;
    if (rows.length) t.classList.add('entete-fixe');
    rows.forEach(function (r) {
      Array.prototype.forEach.call(r.cells, function (c) {
        c.classList.add('th-fixe'); c.dataset.haut = y;
        var bg = getComputedStyle(c).backgroundColor;
        if (!bg || bg === 'transparent' || bg === 'rgba(0, 0, 0, 0)') c.style.backgroundColor = '#F9FAFB';
      });
      y += r.getBoundingClientRect().height;
    });
    // 1re colonne fixe quand le tableau déborde de son cadre sur les côtés
    var deborde = cadre && cadre.scrollWidth > cadre.clientWidth + 4;
    // le tableau a déjà sa propre colonne collée à gauche (registre, saisie des notes) : on la garde
    var corps = t.tBodies[0] && t.tBodies[0].rows[0];
    if (corps && Array.prototype.some.call(corps.cells, function (c) {
      if (c.classList.contains('col-fixe')) return false;
      var cs = getComputedStyle(c); return cs.position === 'sticky' && cs.left !== 'auto';
    })) deborde = false;
    var couvert = 0;   // lignes dont la 1re colonne est prise par une cellule fusionnée (rowspan) d'au-dessus
    Array.prototype.forEach.call(t.rows, function (r) {
      var c = r.cells[0];
      if (!c) return;
      if (couvert > 0) { couvert--; c.classList.remove('col-fixe'); return; }
      couvert = (c.rowSpan || 1) - 1;
      if (deborde && (c.colSpan || 1) <= 2 && r.cells.length > 2) {
        c.classList.add('col-fixe');
        var bg = getComputedStyle(c).backgroundColor;
        if (!bg || bg === 'transparent' || bg === 'rgba(0, 0, 0, 0)') c.style.backgroundColor = c.tagName === 'TH' ? '#F9FAFB' : '#fff';
      } else c.classList.remove('col-fixe');
    });
  }
  /* Position de l'en-tête : sous les barres collées en haut de la page (barre du haut, indicateurs, barre d'outils
     du document). Dans un cadre .tw, l'en-tête descend d'autant que le haut du cadre passe sous ces barres. */
  // titre de section collé (h2 / h3 d'un formulaire) qui précède le tableau dans la même section : l'en-tête se place dessous
  function titreAuDessus(el) {
    var a = el.parentElement;
    for (var i = 0; a && i < 6 && a.tagName !== 'BODY'; i++, a = a.parentElement) {
      var titres = Array.prototype.filter.call(a.children, function (c) {
        return (c.tagName === 'H2' || c.tagName === 'H3' || c.classList.contains('titre-fixe'))
          && (c.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) && getComputedStyle(c).position === 'sticky';
      });
      if (titres.length) return titres[titres.length - 1];
      if (a.tagName === 'FORM') break;
    }
    return null;
  }
  function placerEntetes() {
    var barres = barresHaut();
    $$('main.travail form h2, main.travail form h3, .titre-fixe').forEach(function (h) { h.style.top = barres + 'px'; });
    $$('table.entete-fixe').forEach(function (t) {
      var cadre = t.closest('.tw'), base, titre = titreAuDessus(cadre || t);
      // ligne sous laquelle l'en-tête reste : bas des barres collées, ou bas du titre de section collé
      var haut = titre ? Math.max(barres, titre.getBoundingClientRect().bottom) : barres;
      if (cadre) { var h = cadre.getBoundingClientRect().top; base = Math.max(0, haut - h); }
      else base = haut;
      $$('.th-fixe', t).forEach(function (c) { c.style.top = (base + (+c.dataset.haut || 0)) + 'px'; });
    });
  }
  var placement = false;
  window.addEventListener('scroll', function () {
    if (placement) return; placement = true;
    (window.requestAnimationFrame || setTimeout)(function () { placement = false; placerEntetes(); });
  }, { passive: true });
  function fixerEntetes(racine) { $$('table', racine || document).forEach(fixerTableau); placerEntetes(); }
  var minuterieEntetes;
  function refixer() { clearTimeout(minuterieEntetes); minuterieEntetes = setTimeout(function () { fixerEntetes(document); }, 120); }
  window.SCOLARIS.fixerEntetes = fixerEntetes;
  window.addEventListener('resize', refixer);
  window.addEventListener('load', refixer);
  document.addEventListener('toggle', refixer, true);       // <details> ouverts : tableaux devenus visibles
  document.addEventListener('click', function (e) { if (e.target.closest('[role=tab], .onglet, .tab, summary, [data-onglet]')) refixer(); }, true);
  // tableaux redimensionnés ou ajoutés plus tard par les scripts de la page (statistiques, résultats, onglets)
  var obs = window.ResizeObserver ? new ResizeObserver(refixer) : null;
  document.addEventListener('DOMContentLoaded', function () {
    if (obs) $$('table').forEach(function (t) { obs.observe(t); });
    if (window.MutationObserver) new MutationObserver(function (muts) {
      var neuf = muts.some(function (m) { return Array.prototype.some.call(m.addedNodes, function (n) {
        return n.nodeType === 1 && (n.tagName === 'TABLE' || (n.querySelector && n.querySelector('table'))); }); });
      if (neuf) { if (obs) $$('table').forEach(function (t) { obs.observe(t); }); refixer(); }
    }).observe(document.body, { childList: true, subtree: true });
  });

  function init(racine) {
    $$('.sig-pad', racine).forEach(initSignature);
    $$('.photo-capture', racine).forEach(initPhoto);
    $$('form', racine).forEach(initCascade);
    $$('form', racine).forEach(initGeo);
    $$('form[data-doc]', racine).forEach(initDoc);
    $$('[data-coches]', racine).forEach(initCoches);
    $$('input[type=password]', racine).forEach(initOeil);
    $$('form[data-hors-ligne]', racine).forEach(initHorsLigne);
    fixerEntetes(racine);
    if (racine === document) { majFile(); viderFile(); initMaj();
      var fa = $('#file-attente'); if (fa) fa.addEventListener('click', function (e) { e.preventDefault(); toast('Envoi des saisies en attente…', true); viderFile(); }); }
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
  window.SCOLARIS.init = init;
  document.addEventListener('DOMContentLoaded', function () { init(document); initMenu(); });
})();
