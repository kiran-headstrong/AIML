/* =========================================================================
   Auth pages — login & registration (js/pages/auth.js)

   Registers two guest-only routes with the core router:
     * /login     — email + password sign-in
     * /register  — create account (name, email, password, experience level)

   On success, the JWT access token and user profile are stored in
   localStorage via App.Store and the user is redirected to the dashboard.
   The router's auth guard (App.Router) redirects unauthenticated users to
   /login and prevents authenticated users from reaching these pages.
   ========================================================================= */
(function (App) {
  'use strict';

  const UI = App.UI;
  const Api = App.Api;
  const Store = App.Store;
  const Router = App.Router;

  // Experience levels offered during registration (mirrors the glossary in
  // the requirements doc). Stored on the user and used to tailor interview
  // prep and cover-letter generation later.
  const EXPERIENCE_LEVELS = [
    'Fresher',
    'Junior',
    'Mid-Level',
    'Senior',
    'Lead/Architect',
  ];

  function authShell(title, subtitle, innerHtml) {
    return (
      '<div class="auth-wrap"><div class="auth-card">' +
      '<div class="auth-logo"><span class="brand-mark">JA</span>' +
      '<h1 class="auth-title">' + UI.escape(title) + '</h1>' +
      '<p class="auth-sub">' + UI.escape(subtitle) + '</p></div>' +
      '<div id="auth-error" class="form-error" hidden></div>' +
      innerHtml +
      '</div></div>'
    );
  }

  function showError(message) {
    const el = document.getElementById('auth-error');
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
  }

  function clearError() {
    const el = document.getElementById('auth-error');
    if (el) el.hidden = true;
  }

  function setSubmitting(form, submitting, labelWhenIdle) {
    const btn = form.querySelector('button[type="submit"]');
    if (!btn) return;
    btn.disabled = submitting;
    btn.innerHTML = submitting
      ? '<span class="spinner"></span> Please wait...'
      : UI.escape(labelWhenIdle);
  }

  // ------------------------------------------------------------------ Login
  function renderLogin(view) {
    view.innerHTML = authShell(
      'Welcome back',
      'Sign in to continue to your dashboard',
      '<form id="login-form" novalidate>' +
        '<div class="form-group">' +
          '<label class="form-label" for="login-email">Email</label>' +
          '<input class="form-control" id="login-email" name="email" type="email" ' +
            'autocomplete="email" required placeholder="you@example.com" />' +
        '</div>' +
        '<div class="form-group">' +
          '<label class="form-label" for="login-password">Password</label>' +
          '<input class="form-control" id="login-password" name="password" type="password" ' +
            'autocomplete="current-password" required placeholder="Your password" />' +
        '</div>' +
        '<button class="btn btn-block" type="submit">Sign in</button>' +
      '</form>' +
      '<p class="auth-switch">New here? ' +
        '<a href="#/register">Create an account</a></p>'
    );

    const form = document.getElementById('login-form');
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      clearError();

      const email = form.email.value.trim();
      const password = form.password.value;
      if (!email || !password) {
        showError('Please enter your email and password.');
        return;
      }

      setSubmitting(form, true, 'Sign in');
      try {
        const res = await Api.post('/api/auth/login', {
          body: { email: email, password: password },
        });
        Store.setSession(res.access_token, res.user);
        UI.toast('Signed in successfully.', 'success');
        Router.navigate('/dashboard');
      } catch (err) {
        showError(err.message || 'Unable to sign in. Please try again.');
        setSubmitting(form, false, 'Sign in');
      }
    });
  }

  // --------------------------------------------------------------- Register
  function renderRegister(view) {
    const levelOptions = EXPERIENCE_LEVELS.map(function (lvl) {
      return '<option value="' + UI.escape(lvl) + '">' + UI.escape(lvl) + '</option>';
    }).join('');

    view.innerHTML = authShell(
      'Create your account',
      'Start tailoring your job applications',
      '<form id="register-form" novalidate>' +
        '<div class="form-group">' +
          '<label class="form-label" for="reg-name">Full name</label>' +
          '<input class="form-control" id="reg-name" name="name" type="text" ' +
            'autocomplete="name" required placeholder="Jane Doe" />' +
        '</div>' +
        '<div class="form-group">' +
          '<label class="form-label" for="reg-email">Email</label>' +
          '<input class="form-control" id="reg-email" name="email" type="email" ' +
            'autocomplete="email" required placeholder="you@example.com" />' +
        '</div>' +
        '<div class="form-group">' +
          '<label class="form-label" for="reg-password">Password</label>' +
          '<input class="form-control" id="reg-password" name="password" type="password" ' +
            'autocomplete="new-password" required minlength="6" placeholder="At least 6 characters" />' +
          '<p class="form-hint">Use at least 6 characters.</p>' +
        '</div>' +
        '<div class="form-group">' +
          '<label class="form-label" for="reg-experience">Experience level</label>' +
          '<select class="form-control" id="reg-experience" name="experience_level">' +
            '<option value="">Prefer not to say</option>' + levelOptions +
          '</select>' +
          '<p class="form-hint">Used to tailor interview prep and cover letters.</p>' +
        '</div>' +
        '<button class="btn btn-block" type="submit">Create account</button>' +
      '</form>' +
      '<p class="auth-switch">Already have an account? ' +
        '<a href="#/login">Sign in</a></p>'
    );

    const form = document.getElementById('register-form');
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      clearError();

      const name = form.name.value.trim();
      const email = form.email.value.trim();
      const password = form.password.value;
      const experience = form.experience_level.value;

      if (!name || !email || !password) {
        showError('Please fill in your name, email, and password.');
        return;
      }
      if (password.length < 6) {
        showError('Password must be at least 6 characters.');
        return;
      }

      setSubmitting(form, true, 'Create account');
      try {
        const res = await Api.post('/api/auth/register', {
          body: {
            name: name,
            email: email,
            password: password,
            experience_level: experience || null,
          },
        });
        Store.setSession(res.access_token, res.user);
        UI.toast('Account created. Welcome!', 'success');
        Router.navigate('/dashboard');
      } catch (err) {
        showError(err.message || 'Unable to create account. Please try again.');
        setSubmitting(form, false, 'Create account');
      }
    });
  }

  // ---- Register routes (guest-only; the guard redirects authed users) ----
  App.registerRoute('/login', {
    requiresAuth: false,
    guestOnly: true,
    title: 'Sign in',
    render: renderLogin,
  });

  App.registerRoute('/register', {
    requiresAuth: false,
    guestOnly: true,
    title: 'Register',
    render: renderRegister,
  });
})(window.App);
