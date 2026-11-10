/* =========================================================================
   Runtime frontend configuration.

   `window.API_BASE_URL` controls where the SPA sends API requests. It is read
   by app.js (see `App.Config.apiBase`).

     * Local dev (open index.html or a static server on another port):
         leave this unset / empty and app.js falls back to
         http://localhost:8000 (the default backend address).

     * Containerised (served by nginx which reverse-proxies /api to the
         backend): the Docker build replaces this file with one that sets
         API_BASE_URL = "" so requests are same-origin and hit the proxy.

   Override by editing the value below, or by defining window.API_BASE_URL
   before this script loads.
   ========================================================================= */
window.API_BASE_URL = window.API_BASE_URL || '';
