// service-worker.js — Flife PWA 離線快取
// 只快取「殼」（HTML/CSS/JS/圖示），API資料一律走網路，不快取計算結果。

const CACHE_NAME = "flife-shell-v1";
const SHELL_FILES = [
  "./",
  "./index.html",
  "./style.css",
  "./app.js",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // API 請求（/api/...）一律走網路，不快取——計算結果必須即時
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  // 靜態殼：cache-first，抓不到再回網路
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
