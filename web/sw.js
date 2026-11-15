const C = "finn-v3";
self.addEventListener("install", e => e.waitUntil(caches.open(C).then(c => c.addAll(["./", "index.html", "styles.css", "app.js", "config.js"])).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const u = new URL(e.request.url);
  if (u.origin !== self.location.origin || u.pathname.includes("/api/")) return;   // live API: never cache
  e.respondWith(fetch(e.request).then(r => { const cp = r.clone(); caches.open(C).then(c => c.put(e.request, cp)); return r; }).catch(() => caches.match(e.request)));
});
