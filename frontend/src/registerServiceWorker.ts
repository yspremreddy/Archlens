export function registerServiceWorker(): void {
  if (!('serviceWorker' in navigator)) return
  if (import.meta.env.DEV) return // avoid caching interference during development
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // offline caching is a progressive enhancement — failure is silent, non-fatal
    })
  })
}
