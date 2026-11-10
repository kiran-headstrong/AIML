/* =========================================================================
   Placeholder pages (js/pages/placeholders.js)

   Registers the authenticated feature routes referenced by the sidebar so
   the app shell, navigation, and auth guard are fully functional now. These
   are intentionally minimal stubs; tasks 18–20 replace each with the real
   page module (jd.js, resume.js, match.js, interview.js, cover_letter.js,
   compare.js, dashboard.js).

   NOTE: once a real page module registers the same route path with
   App.registerRoute(), it overrides the stub here (load order: this file is
   included before the feature modules in index.html).
   ========================================================================= */
(function (App) {
  'use strict';

  const UI = App.UI;

  function stub(title, description) {
    return function (view) {
      view.innerHTML =
        '<div class="page-header">' +
          '<h1 class="page-title">' + UI.escape(title) + '</h1>' +
          '<p class="page-subtitle">' + UI.escape(description) + '</p>' +
        '</div>' +
        '<div class="card"><div class="empty-state">' +
          '<div class="empty-icon">🚧</div>' +
          '<h2>Coming soon</h2>' +
          '<p class="muted">This section is under construction.</p>' +
        '</div></div>';
    };
  }

  const pages = [
    ['/dashboard', 'Dashboard', 'Track all your analyzed and applied jobs in one place.'],
    ['/jd', 'Scrape Job Description', 'Paste a LinkedIn or Naukri URL to extract the job description.'],
    ['/resume', 'My Resume', 'Upload and manage your base resume.'],
    ['/match', 'Match & Suggestions', 'See how your resume matches a job and get tailored suggestions.'],
    ['/interview', 'Interview Prep', 'Generate topics and Q&A tailored to the role.'],
    ['/cover-letter', 'Cover Letter', 'Generate a tailored cover letter for each application.'],
    ['/compare', 'Compare JDs', 'Compare multiple job descriptions side by side.'],
  ];

  pages.forEach(function (p) {
    App.registerRoute(p[0], {
      requiresAuth: true,
      title: p[1],
      render: stub(p[1], p[2]),
    });
  });
})(window.App);
