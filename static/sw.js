const CACHE_NAME = 'mygym-shell-v6';
const APP_SHELL = [
    '/static/app.js?v=7', '/static/style.css?v=2',
    '/static/auth.js?v=3', '/static/auth.css?v=2',
    '/static/manifest.json', '/static/icon.png', '/static/icon-192.png'
];
self.addEventListener('install', event => {
    event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)));
    self.skipWaiting();
});
self.addEventListener('activate', event => {
    event.waitUntil(caches.keys().then(keys => Promise.all(keys
        .filter(key => key.startsWith('mygym-shell-') && key !== CACHE_NAME)
        .map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
    const request = event.request;
    const url = new URL(request.url);
    if (request.method !== 'GET' || url.origin !== self.location.origin ||
        url.pathname.startsWith('/api/') || ['/login','/accounts','/account'].includes(url.pathname)) return;
    if (request.mode === 'navigate') {
        event.respondWith(fetch(request).then(response => {
            // Never store a login redirect under an authenticated page URL.
            if (response.ok && !response.redirected) {
                const copy = response.clone();
                event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.put(request, copy)));
            }
            return response;
        }).catch(async () => (await caches.match(request)) || new Response('Connection unavailable. Please reconnect.', {status:503,headers:{'Content-Type':'text/plain; charset=utf-8'}})));
        return;
    }
    event.respondWith(caches.match(request).then(cached => cached || fetch(request).then(response => {
        if (response.ok && !response.redirected) {
            const copy=response.clone();
            event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.put(request,copy)));
        }
        return response;
    })));
});
