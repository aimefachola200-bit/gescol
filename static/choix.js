/* SCOLARIS v1.18 — Choix faciles sur téléphone et tablette.
   Sur écran tactile, les listes de suggestions (input list=…, y compris les champs data-geo : département, commune,
   arrondissement, village, lieu de naissance) et les longues listes déroulantes (plus de 12 choix) s'ouvrent dans un
   panneau plein écran placé au-dessus du clavier (visualViewport) : recherche en haut, résultats juste en dessous,
   gros boutons, « Utiliser ce que j'ai tapé », Fermer ; la touche Retour du téléphone ferme le panneau.
   Le choix déclenche les événements input / change habituels : les cascades data-geo de scolaris.js suivent.
   Sur ordinateur (pointeur fin), rien ne change. Exclure un champ : data-choix="non". */
(function (global) {
  'use strict';
  if (global.Choix) return;
  const doc = global.document;
  const SEUIL_SELECT = 12;
  const tactile = () => !!(global.matchMedia && global.matchMedia('(pointer: coarse)').matches) && !global.CHOIX_DESACTIVE;
  const sansAccent = (s) => String(s == null ? '' : s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

  /* ------------------------------------------------------------------ sélecteur tactile */
  let ouvert = null;
  function style() {
    if (doc.getElementById('choix-style')) return;
    const s = doc.createElement('style'); s.id = 'choix-style';
    s.textContent = `
.choix-voile{position:fixed;inset:0;background:rgba(16,24,40,.45);z-index:2147483000}
.choix-panneau{position:fixed;left:0;right:0;top:0;height:100vh;background:#fff;color:#1D2939;display:flex;flex-direction:column;z-index:2147483001;font:16px/1.35 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;box-shadow:0 -4px 24px rgba(0,0,0,.2)}
.choix-tete{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid #D0D5DD;background:#1F4E79;color:#fff}
.choix-tete b{flex:1;font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.choix-tete button{background:rgba(255,255,255,.15);color:#fff;border:0;border-radius:8px;min-width:44px;min-height:40px;font-size:15px;padding:0 12px}
.choix-cherche{padding:8px 12px;border-bottom:1px solid #EAECF0}
.choix-cherche input{width:100%;box-sizing:border-box;font-size:17px;padding:11px 12px;border:2px solid #2E6DA4;border-radius:10px;outline:none}
.choix-libre{margin:6px 12px 0;padding:11px 12px;border:1px dashed #2E6DA4;border-radius:10px;background:#EEF4FA;color:#1F4E79;font-weight:600;text-align:left;font-size:15px}
.choix-liste{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;padding:4px 0 12px}
.choix-item{display:block;width:100%;text-align:left;background:none;border:0;border-bottom:1px solid #F2F4F7;padding:12px 14px;min-height:48px;font-size:16px;color:#1D2939}
.choix-item small{display:block;color:#667085;font-size:12.5px;margin-top:2px}
.choix-item.actuel{background:#EEF4FA;font-weight:600}
.choix-item:active{background:#DCE8F5}
.choix-vide{padding:16px;color:#667085}
.choix-plus{padding:10px 14px;color:#667085;font-size:13px}`;
    doc.head.appendChild(s);
  }
  function placer() {
    if (!ouvert) return;
    const vv = global.visualViewport;
    const h = vv ? vv.height : global.innerHeight, t = vv ? vv.offsetTop : 0;
    ouvert.panneau.style.top = t + 'px'; ouvert.panneau.style.height = h + 'px';
  }
  function libelleChamp(el) {
    const lab = (el.id && doc.querySelector('label[for="' + CSS.escape(el.id) + '"]')) || el.closest('label') || (el.parentElement && el.parentElement.querySelector(':scope > label, :scope > span'));
    let t = '';
    if (lab && lab !== el) {   // texte du libellé sans le contenu des champs qu'il entoure (options d'une liste…)
      const c = lab.cloneNode(true);
      c.querySelectorAll('select, option, datalist, input, textarea, button').forEach(x => x.remove());
      t = c.textContent;
    }
    return ((t && t.trim()) || el.getAttribute('aria-label') || el.placeholder || el.name || 'Choisir').replace(/\s+/g, ' ').trim().slice(0, 80);
  }
  async function optionsDe(el) {
    if (el.tagName === 'SELECT') return [...el.options].filter(o => !o.disabled || o.value === '').map(o => ({ v: o.value, t: o.textContent.trim(), l: '' }));
    const id = el.getAttribute('list'), dl = id && doc.getElementById(id);
    return dl ? [...dl.options].map(o => ({ v: o.value, t: o.value, l: o.label && o.label !== o.value ? o.label : '' })) : [];
  }
  function choisir(el, v) {
    if (el.value !== v) {
      el.value = v;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    } else el.dispatchEvent(new Event('change', { bubbles: true }));
  }
  function fermer(parRetour) {
    if (!ouvert) return;
    const o = ouvert; ouvert = null;
    o.voile.remove(); o.panneau.remove();
    if (global.visualViewport) { global.visualViewport.removeEventListener('resize', placer); global.visualViewport.removeEventListener('scroll', placer); }
    doc.documentElement.style.overflow = o.overflow;
    if (!parRetour && o.historique && history.state && history.state.choix) { o.ignorerRetour = true; history.back(); }
  }
  global.addEventListener('popstate', () => { if (ouvert) fermer(true); });
  async function ouvrir(el) {
    if (ouvert || el.disabled || el.readOnly) return;
    style();
    const estSelect = el.tagName === 'SELECT';
    const voile = doc.createElement('div'); voile.className = 'choix-voile';
    const panneau = doc.createElement('div'); panneau.className = 'choix-panneau'; panneau.setAttribute('role', 'dialog'); panneau.setAttribute('aria-modal', 'true');
    const titre = libelleChamp(el);
    panneau.innerHTML = '<div class="choix-tete"><b></b><button type="button" class="choix-fermer" aria-label="Fermer">✕ Fermer</button></div>'
      + '<div class="choix-cherche"><input type="search" enterkeyhint="done" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="Rechercher…" aria-label="Rechercher"></div>'
      + '<button type="button" class="choix-libre" hidden></button><div class="choix-liste" role="listbox"></div>';
    panneau.querySelector('b').textContent = titre;
    doc.body.append(voile, panneau);
    ouvert = { el, voile, panneau, overflow: doc.documentElement.style.overflow, historique: false };
    doc.documentElement.style.overflow = 'hidden';
    try { history.pushState(Object.assign({}, history.state || {}, { choix: 1 }), ''); ouvert.historique = true; } catch (e) { /* sans historique */ }
    placer();
    if (global.visualViewport) { global.visualViewport.addEventListener('resize', placer); global.visualViewport.addEventListener('scroll', placer); }
    const champ = panneau.querySelector('input'), liste = panneau.querySelector('.choix-liste'), libre = panneau.querySelector('.choix-libre');
    panneau.querySelector('.choix-fermer').onclick = () => fermer();
    voile.onclick = () => fermer();
    liste.innerHTML = '<div class="choix-vide">Chargement…</div>';
    const opts = await optionsDe(el);
    if (!ouvert || ouvert.el !== el) return;
    const actuel = el.value;
    champ.value = estSelect ? '' : (el.value || '');
    function dessiner() {
      const q = sansAccent(champ.value.trim());
      const res = q ? opts.filter(o => sansAccent(o.t + ' ' + o.l + ' ' + o.v).indexOf(q) >= 0) : opts;
      // les réponses qui commencent par la recherche d'abord
      if (q) res.sort((a, b) => (sansAccent(a.t).startsWith(q) ? 0 : 1) - (sansAccent(b.t).startsWith(q) ? 0 : 1));
      const max = 250;
      liste.replaceChildren();
      res.slice(0, max).forEach(o => {
        const b = doc.createElement('button'); b.type = 'button'; b.className = 'choix-item' + (o.v === actuel && actuel !== '' ? ' actuel' : '');
        b.setAttribute('role', 'option'); b.textContent = o.t || '—';
        if (o.l) { const s = doc.createElement('small'); s.textContent = o.l; b.appendChild(s); }
        b.onclick = () => { fermer(); choisir(el, o.v); };
        liste.appendChild(b);
      });
      if (!res.length) { const d = doc.createElement('div'); d.className = 'choix-vide'; d.textContent = estSelect ? 'Aucun choix ne correspond.' : 'Rien dans la liste : utilisez ce que vous avez tapé.'; liste.appendChild(d); }
      if (res.length > max) { const d = doc.createElement('div'); d.className = 'choix-plus'; d.textContent = (res.length - max) + ' autre(s) : précisez la recherche.'; liste.appendChild(d); }
      const t = champ.value.trim();
      libre.hidden = estSelect || !t || opts.some(o => o.v === t);
      libre.textContent = 'Utiliser « ' + t + ' »';
    }
    libre.onclick = () => { const t = champ.value.trim(); fermer(); choisir(el, t); };
    champ.addEventListener('input', dessiner);
    champ.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') fermer();
      if (e.key === 'Enter') { e.preventDefault(); const p = liste.querySelector('.choix-item'); if (!estSelect && champ.value.trim() && (!p || sansAccent(p.textContent).indexOf(sansAccent(champ.value.trim())) !== 0)) libre.click(); else if (p) p.click(); }
    });
    dessiner();
    setTimeout(() => { if (ouvert && ouvert.el === el) champ.focus({ preventScroll: true }); }, 30);
  }
  const concerne = (el) => {
    if (!el || !el.tagName) return false;
    if (el.closest && el.closest('.choix-panneau, [data-choix="non"]')) return false;
    if (el.dataset && el.dataset.choix === 'non') return false;
    if (el.tagName === 'SELECT') return !el.multiple && el.options.length > SEUIL_SELECT;
    if (el.tagName === 'INPUT') return !!el.getAttribute('list') && /^(text|search|)$/.test(el.type || '') && !el.readOnly;
    return false;
  };
  function intercepter(e) {
    if (!tactile()) return;
    const el = e.target && e.target.closest ? e.target.closest('input, select') : null;
    if (!el) return;
    if (!concerne(el)) return;
    e.preventDefault(); e.stopPropagation();
    if (e.type !== 'focusin') ouvrir(el);
    else { el.blur(); ouvrir(el); }
  }
  // un simple toucher ouvre le panneau ; faire glisser le doigt (défiler la page) ne l'ouvre pas
  let depart = null;
  const cible = (e) => { const el = e.target && e.target.closest ? e.target.closest('input, select') : null; return el && concerne(el) ? el : null; };
  doc.addEventListener('touchstart', (e) => { const t = e.touches[0]; depart = tactile() && cible(e) && t ? { x: t.clientX, y: t.clientY } : null; }, { capture: true, passive: true });
  doc.addEventListener('touchend', (e) => {
    if (!depart || !tactile()) return;
    const el = cible(e), t = e.changedTouches[0], d = depart; depart = null;
    if (!el || !t || Math.abs(t.clientX - d.x) > 10 || Math.abs(t.clientY - d.y) > 10) return;
    e.preventDefault(); e.stopPropagation(); ouvrir(el);
  }, { capture: true, passive: false });
  doc.addEventListener('mousedown', intercepter, true);
  doc.addEventListener('focusin', (e) => { if (tactile() && !ouvert && concerne(e.target)) intercepter(e); }, true);

  global.Choix = { ouvrir, fermer, concerne, SEUIL_SELECT };
})(window);
