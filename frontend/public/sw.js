// Hand-rolled service worker (no vite-plugin-pwa — engineering guideline 8).
// Caches this app's own static build assets (JS/CSS/HTML/fonts) for
// offline reload; API calls to the ArchLens backend are NEVER cached
// here since findings/evidence must always reflect live, current data.
const CACHE_NAME = 'archlens-static-v1'

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(['/', '/index.html'])),
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))),
    ),
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)

  // Only handle same-origin GET requests for our own static assets.
  // Anything going to the API (a different origin/port in dev, or
  // same-origin /api/* in a proxied prod deploy) is left untouched so
  // review/search results are always fresh, never served stale.
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api')) return

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached
      return fetch(event.request)
        .then((response) => {
          if (response.ok && (url.pathname === '/' || /\.(js|css|svg|png|woff2?)$/.test(url.pathname))) {
            const clone = response.clone()
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone))
          }
          return response
        })
        .catch(() => cached)
    }),
  )
})
