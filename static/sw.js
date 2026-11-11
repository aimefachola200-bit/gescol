/* GESCOL – service worker
   - Les pages viennent toujours du serveur (données à jour, rien de confidentiel en cache).
   - Les fichiers statiques (style, icônes) sont mis en cache pour un démarrage rapide.
   - Sans connexion au serveur, une page explicative s'affiche.
   - v1.8 : les pages de saisie en classe (appel, notes, Ma classe) déjà ouvertes restent consultables sans connexion
     (copie locale, effacée à la déconnexion) ; les saisies faites hors ligne sont envoyées plus tard (gescol.js). */
const VERSION = "gescol-2.3.4";
const PAGES = "gescol-pages";
const CLASSE = /^\/(appel\/\d+\/|evaluations\/\d+\/(saisie|donnees\.json)|ma-classe)/;
const STATIQUES = ["/hors-ligne", "/static/style.css", "/static/sombre.css", "/static/theme.js", "/static/choix.js", "/static/icons/icon-192.png", "/static/icons/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(STATIQUES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((cles) => Promise.all(cles.filter((k) => k !== VERSION && k !== PAGES).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  if (url.pathname === "/logout") {               // déconnexion : plus aucune page de classe sur l'appareil
    caches.delete(PAGES);
  }
  if (CLASSE.test(url.pathname)) {                 // réseau d'abord, copie locale en secours
    e.respondWith(
      fetch(req).then((rep) => {
        if (rep.ok && !rep.redirected) { const copie = rep.clone(); caches.open(PAGES).then((c) => c.put(req, copie)); }
        return rep;
      }).catch(() => caches.open(PAGES).then((c) => c.match(req)).then((m) => m || caches.match("/hors-ligne")))
    );
    return;
  }
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/hors-ligne")));
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(
      caches.match(req).then((cache) => {
        const reseau = fetch(req).then((rep) => {
          if (rep.ok) caches.open(VERSION).then((c) => c.put(req, rep.clone()));
          return rep;
        }).catch(() => cache);
        return cache || reseau;
      })
    );
  }
});
