/* Container build of config.js — served by nginx which reverse-proxies /api
   to the backend. Using the page origin makes all API calls same-origin so no
   CORS configuration is required. This file replaces js/config.js inside the
   frontend Docker image. */
window.API_BASE_URL = window.location.origin;
