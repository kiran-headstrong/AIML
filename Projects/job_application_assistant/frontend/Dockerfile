# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Frontend image: static SPA served by nginx.
#
# nginx also reverse-proxies /api (and /docs, /health) to the backend service
# so the browser talks to a single origin and no CORS config is required.
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine

# Static SPA assets.
COPY . /usr/share/nginx/html

# Use the container config that routes API calls to the same origin (nginx
# proxies them to the backend), replacing the local-dev default.
COPY js/config.container.js /usr/share/nginx/html/js/config.js

# nginx site config with API reverse proxy.
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
