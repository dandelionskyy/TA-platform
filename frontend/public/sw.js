// Simple PWA service worker for offline caching
const CACHE_NAME = 'ta-platform-v5';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/static/images/logo.png',
  '/static/images/bot_avatar.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Only cache GET requests, skip API calls
  if (event.request.method !== 'GET' || event.request.url.includes('/api/')) {
    return;
  }
  event.respondWith(fetch(event.request).then((response) => {
    if (response.ok) caches.open(CACHE_NAME).then((cache) => cache.put(event.request, response.clone()));
    return response;
  }).catch(() => caches.match(event.request).then(cached => cached || caches.match('/index.html'))));
});
