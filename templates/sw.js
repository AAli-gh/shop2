// Service worker (served at /sw.js): when a page can't be fetched because the connection is gone,
// show the cached «no internet» page instead of the browser's own error. Nothing else is cached,
// so the shop never serves stale pages or prices.
const CACHE = "shop-offline-v1";
const OFFLINE_URL = "/offline/";
const ASSETS = [
  OFFLINE_URL,
  "/static/img/states/room.jpg",
  "/static/fonts/Vazirmatn-Regular.woff2",
  "/static/fonts/Vazirmatn-Bold.woff2",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }
  // the offline page's own picture and fonts, only when the network can't deliver them
  if (ASSETS.includes(new URL(request.url).pathname)) {
    event.respondWith(fetch(request).catch(() => caches.match(request, { ignoreSearch: true })));
  }
});
