const PRECACHE = 'stretch-coach-precache-v1';
const RUNTIME = 'stretch-coach-runtime-v1';

const PRECACHE_URLS = [
  "./",
  "/",
  "./index.html",
  "./config.production.js",
  "./exercises.json",
  "./manifest.webmanifest",
  "./service-worker.js",
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches
      .open(PRECACHE)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches
      .keys()
      .then(keys => Promise.all(keys.filter(key => ![PRECACHE, RUNTIME].includes(key)).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const { request } = event;

  if (request.method !== 'GET') {
    return;
  }

  const accept = request.headers.get('Accept') || '';
  const isHtml = request.mode === 'navigate' || request.destination === 'document' || accept.includes('text/html');
  const wantsJson = accept.includes('application/json') || accept.includes('text/json');
  const isJsonUrl = request.url.endsWith('.json');
  const isApiRequest = request.url.includes('/api/');

  if (isHtml || wantsJson || isJsonUrl || isApiRequest) {
    event.respondWith(
      fetch(request, { cache: 'no-store' })
        .then(networkResponse => {
          const responseClone = networkResponse.clone();
          caches.open(RUNTIME).then(cache => cache.put(request, responseClone));
          return networkResponse;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(cachedResponse => {
      if (cachedResponse) {
        return cachedResponse;
      }

      return fetch(request).then(networkResponse => {
        if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
          return networkResponse;
        }

        const responseClone = networkResponse.clone();
        caches.open(RUNTIME).then(cache => cache.put(request, responseClone));
        return networkResponse;
      });
    })
  );
});
