/* =========================================================================
   Job Application Assistant — Core application module (app.js)

   Provides, under the global `App` namespace:
     * Config        — API base URL
     * Store         — JWT token + current user in localStorage
     * Api           — fetch wrapper with JWT auth headers + error parsing
     * Router        — hash-based SPA router with route guards
     * UI            — toast notifications, small DOM helpers
     * registerRoute — page modules register their views here

   Page modules (auth.js, placeholders.js, ...) call `App.registerRoute()`
   to plug into the router. `App.start()` boots everything.
   ========================================================================= */
(function (window) {
  'use strict';

  // ------------------------------------------------------------------ Config
  const Config = {
    // Backend runs on :8000 by default (see backend/config.py). Allow an
    // override via a global set before this script loads.
    apiBase: window.API_BASE_URL || 'http://localhost:8000',
    tokenKey: 'jaa_token',
    userKey: 'jaa_user',
    // Remembers the JD the user is currently working with so the core feature
    // pages (match, interview, cover letter, ...) can share context without a
    // backend "current JD" concept. Set when a JD is scraped/selected.
    selectedJdKey: 'jaa_selected_jd',
  };

  // ------------------------------------------------------------------- Store
  // Thin wrapper over localStorage for the auth token and cached user.
  const Store = {
    getToken() {
      return localStorage.getItem(Config.tokenKey);
    },
    setToken(token) {
      if (token) localStorage.setItem(Config.tokenKey, token);
    },
    getUser() {
      const raw = localStorage.getItem(Config.userKey);
      try {
        return raw ? JSON.parse(raw) : null;
      } catch (e) {
        return null;
      }
    },
    setUser(user) {
      if (user) localStorage.setItem(Config.userKey, JSON.stringify(user));
    },
    setSession(token, user) {
      this.setToken(token);
      this.setUser(user);
    },
    clear() {
      localStorage.removeItem(Config.tokenKey);
      localStorage.removeItem(Config.userKey);
      localStorage.removeItem(Config.selectedJdKey);
    },
    isAuthenticated() {
      return !!this.getToken();
    },
    // --- Selected JD context (shared across core feature pages) ----------
    getSelectedJd() {
      const raw = localStorage.getItem(Config.selectedJdKey);
      try {
        return raw ? JSON.parse(raw) : null;
      } catch (e) {
        return null;
      }
    },
    setSelectedJd(jd) {
      if (!jd || !jd.id) return;
      // Persist a lightweight summary only (id + display fields).
      localStorage.setItem(
        Config.selectedJdKey,
        JSON.stringify({
          id: jd.id,
          job_title: jd.job_title || '',
          company_name: jd.company_name || '',
        })
      );
    },
  };

  // --------------------------------------------------------------------- Api
  // Error carrying the parsed backend error envelope + HTTP status.
  class ApiError extends Error {
    constructor(message, status, type, details) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
      this.type = type;
      this.details = details;
    }
  }

  const Api = {
    /**
     * Perform an authenticated JSON request.
     * @param {string} method  HTTP method
     * @param {string} path    Path beginning with `/api/...`
     * @param {object} [options] { body, query, raw, headers }
     *        - body: object serialized to JSON, or FormData passed as-is
     *        - query: object of query params
     *        - raw: when true, resolve with the Response (for file downloads)
     */
    async request(method, path, options) {
      options = options || {};
      let url = Config.apiBase + path;

      if (options.query) {
        const qs = new URLSearchParams();
        Object.keys(options.query).forEach(function (k) {
          const v = options.query[k];
          if (v !== undefined && v !== null && v !== '') qs.append(k, v);
        });
        const str = qs.toString();
        if (str) url += '?' + str;
      }

      const headers = Object.assign({}, options.headers || {});
      const token = Store.getToken();
      if (token) headers['Authorization'] = 'Bearer ' + token;

      let body;
      if (options.body instanceof FormData) {
        body = options.body; // let the browser set the multipart boundary
      } else if (options.body !== undefined) {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify(options.body);
      }

      let response;
      try {
        response = await fetch(url, { method: method, headers: headers, body: body });
      } catch (networkErr) {
        throw new ApiError(
          'Unable to reach the server. Check your connection and try again.',
          0,
          'network_error',
          null
        );
      }

      // Session expired / invalid token -> force re-login.
      if (response.status === 401 && Store.isAuthenticated()) {
        Store.clear();
        UI.toast('Your session expired. Please log in again.', 'error');
        Router.navigate('/login');
      }

      if (options.raw) {
        if (!response.ok) await Api._throwFromResponse(response);
        return response;
      }

      // No content.
      if (response.status === 204) return null;

      let data = null;
      const text = await response.text();
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (e) {
          data = text;
        }
      }

      if (!response.ok) {
        Api._throwParsed(response.status, data);
      }
      return data;
    },

    async _throwFromResponse(response) {
      let data = null;
      try {
        data = await response.json();
      } catch (e) {
        /* ignore */
      }
      Api._throwParsed(response.status, data);
    },

    _throwParsed(status, data) {
      // Backend envelope: { error: { type, message, details } }
      let message = 'Request failed (' + status + ').';
      let type = 'error';
      let details = null;
      if (data && data.error) {
        message = data.error.message || message;
        type = data.error.type || type;
        details = data.error.details || null;
      } else if (data && typeof data.detail === 'string') {
        message = data.detail;
      }
      throw new ApiError(message, status, type, details);
    },

    get(path, options) { return this.request('GET', path, options); },
    post(path, options) { return this.request('POST', path, options); },
    patch(path, options) { return this.request('PATCH', path, options); },
    del(path, options) { return this.request('DELETE', path, options); },
  };

  // ---------------------------------------------------------------------- UI
  const UI = {
    toast(message, variant) {
      const container = document.getElementById('toast-container');
      if (!container) return;
      const el = document.createElement('div');
      el.className = 'toast toast-' + (variant || 'info');
      el.textContent = message;
      container.appendChild(el);
      setTimeout(function () {
        el.style.opacity = '0';
        setTimeout(function () { el.remove(); }, 200);
      }, 3500);
    },

    /** Escape untrusted text for safe insertion into HTML. */
    escape(value) {
      if (value === null || value === undefined) return '';
      return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    },

    /** Render a loading indicator into the main view. */
    renderLoading(text) {
      return '<div class="loading"><span class="spinner"></span>' +
        UI.escape(text || 'Loading...') + '</div>';
    },

    setView(html) {
      const view = document.getElementById('view');
      if (view) view.innerHTML = html;
    },
  };

  // ------------------------------------------------------------------ Router
  // Routes registered by page modules: { path, render, requiresAuth, title }
  const routes = {};

  function registerRoute(path, config) {
    routes[path] = Object.assign({ requiresAuth: true }, config);
  }

  const Router = {
    navigate(path) {
      const target = '#' + (path.charAt(0) === '/' ? path : '/' + path);
      if (window.location.hash === target) {
        Router.resolve();
      } else {
        window.location.hash = target;
      }
    },

    current() {
      const hash = window.location.hash.replace(/^#/, '') || '/';
      // Strip query portion (not used for route matching).
      return hash.split('?')[0];
    },

    async resolve() {
      let path = Router.current();
      if (path === '/' || path === '') {
        path = Store.isAuthenticated() ? '/dashboard' : '/login';
      }

      const route = routes[path] || routes['__notfound__'];

      // ---- Auth guard -------------------------------------------------
      if (route && route.requiresAuth && !Store.isAuthenticated()) {
        Router.navigate('/login');
        return;
      }
      // Prevent authenticated users from seeing login/register.
      if (route && route.guestOnly && Store.isAuthenticated()) {
        Router.navigate('/dashboard');
        return;
      }

      Shell.update(route);

      if (!route) {
        UI.setView('<div class="empty-state"><div class="empty-icon">🔍</div>' +
          '<h2>Page not found</h2><p class="muted">The page you requested does not exist.</p></div>');
        return;
      }

      Shell.setActiveNav(path);

      try {
        await route.render(document.getElementById('view'), Router.query());
      } catch (err) {
        if (err instanceof ApiError) {
          UI.setView('<div class="empty-state"><div class="empty-icon">⚠️</div>' +
            '<h2>Something went wrong</h2><p class="muted">' + UI.escape(err.message) + '</p></div>');
        } else {
          console.error(err);
          UI.setView('<div class="empty-state"><div class="empty-icon">⚠️</div>' +
            '<h2>Unexpected error</h2><p class="muted">Please try again.</p></div>');
        }
      }
    },

    /** Parse the query string portion of the current hash into an object. */
    query() {
      const hash = window.location.hash.replace(/^#/, '');
      const idx = hash.indexOf('?');
      const out = {};
      if (idx === -1) return out;
      new URLSearchParams(hash.slice(idx + 1)).forEach(function (v, k) {
        out[k] = v;
      });
      return out;
    },
  };

  // ------------------------------------------------------------------- Shell
  // Controls navbar/sidebar visibility and active-link highlighting based on
  // the active route and auth state.
  const Shell = {
    update(route) {
      const navbar = document.getElementById('navbar');
      const sidebar = document.getElementById('sidebar');
      const view = document.getElementById('view');
      const authed = Store.isAuthenticated();
      const chromeless = route && route.guestOnly;

      const showChrome = authed && !chromeless;
      if (navbar) navbar.hidden = !showChrome;
      if (sidebar) sidebar.hidden = !showChrome;
      if (view) view.classList.toggle('auth-view', !showChrome);

      // Populate the current user's name in the navbar.
      const user = Store.getUser();
      const nameEl = document.getElementById('user-name');
      if (nameEl && user) nameEl.textContent = user.name || user.email || '';

      Shell.closeSidebar();
    },

    setActiveNav(path) {
      const base = '/' + (path.split('/')[1] || '');
      document.querySelectorAll('.nav-link').forEach(function (link) {
        const href = (link.getAttribute('href') || '').replace(/^#/, '');
        link.classList.toggle('active', href === base || href === path);
      });
    },

    toggleSidebar() {
      const sidebar = document.getElementById('sidebar');
      const backdrop = document.getElementById('sidebar-backdrop');
      if (!sidebar) return;
      const open = sidebar.classList.toggle('open');
      if (backdrop) backdrop.hidden = !open;
      const toggle = document.getElementById('nav-toggle');
      if (toggle) toggle.setAttribute('aria-expanded', String(open));
    },

    closeSidebar() {
      const sidebar = document.getElementById('sidebar');
      const backdrop = document.getElementById('sidebar-backdrop');
      if (sidebar) sidebar.classList.remove('open');
      if (backdrop) backdrop.hidden = true;
      const toggle = document.getElementById('nav-toggle');
      if (toggle) toggle.setAttribute('aria-expanded', 'false');
    },

    bindChrome() {
      const toggle = document.getElementById('nav-toggle');
      if (toggle) toggle.addEventListener('click', Shell.toggleSidebar);

      const backdrop = document.getElementById('sidebar-backdrop');
      if (backdrop) backdrop.addEventListener('click', Shell.closeSidebar);

      const logout = document.getElementById('logout-btn');
      if (logout) {
        logout.addEventListener('click', function () {
          Store.clear();
          UI.toast('You have been logged out.', 'info');
          Router.navigate('/login');
        });
      }
    },
  };

  // -------------------------------------------------------------------- Boot
  const App = {
    Config: Config,
    Store: Store,
    Api: Api,
    ApiError: ApiError,
    UI: UI,
    Router: Router,
    Shell: Shell,
    registerRoute: registerRoute,

    start() {
      Shell.bindChrome();
      window.addEventListener('hashchange', Router.resolve);
      Router.resolve();
    },
  };

  window.App = App;
})(window);
