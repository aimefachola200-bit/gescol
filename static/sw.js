/* GESCOL – service worker
   - Les pages viennent toujours du serveur (données à jour, rien de confidentiel en cache).
   - Les fichiers statiques (style, icônes) sont mis en cache pour un démarrage rapide.
   - Sans connexion au serveur, une page explicative s'affiche. */
const VERSION = "gescol-1.5.0";
const STATIQUES = ["/hors-ligne", "/static/style.css", "/static/icons/icon-192.png", "/static/icons/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(STATIQUES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((cles) => Promise.all(cles.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

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
