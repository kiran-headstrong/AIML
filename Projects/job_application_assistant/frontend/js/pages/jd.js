/* =========================================================================
   JD scraping page (js/pages/jd.js)

   Route: #/jd

   Lets the user paste a LinkedIn or Naukri job posting URL and scrape it.
   On success it renders a confirmation view with:
     * a pretty-printed, structured view of the scraped JD
       (title, company, location, experience, description, required &
        preferred skills) — Requirements 1.1, 1.2, 1.5, 15.1, 15.2
     * the extracted tech stack split into Required / Nice-to-have
       categories — Requirements 2.1, 2.2, 2.3

   The scraped JD is remembered as the "selected JD" (App.Store) so the user
   can continue to matching, interview prep, etc. Unsupported URLs
   (Requirement 1.3) and network/fetch failures (Requirement 1.4) surface as
   inline error messages.

   This module registers the /jd route, overriding the placeholder stub (it
   is loaded after placeholders.js in index.html).
   ========================================================================= */
(function (App) {
  'use strict';

  const UI = App.UI;
  const Api = App.Api;
  const Store = App.Store;
  const Router = App.Router;
  const ApiError = App.ApiError;

  // Friendly labels for tech-stack categories returned by the backend.
  const CATEGORY_LABELS = {
    language: 'Language',
    framework: 'Framework',
    database: 'Database',
    cloud: 'Cloud',
    tool: 'Tool',
  };

  function header() {
    return (
      '<div class="page-header">' +
        '<h1 class="page-title">Scrape Job Description</h1>' +
        '<p class="page-subtitle">Paste a LinkedIn or Naukri job URL to ' +
        'extract and analyze the posting.</p>' +
      '</div>'
    );
  }

  function formCard() {
    return (
      '<div class="card">' +
        '<form id="jd-form" novalidate>' +
          '<div id="jd-error" class="form-error" hidden></div>' +
          '<div class="form-group">' +
            '<label class="form-label" for="jd-url">Job posting URL</label>' +
            '<input class="form-control" id="jd-url" name="url" type="url" ' +
              'placeholder="https://www.linkedin.com/jobs/view/..." ' +
              'autocomplete="off" required />' +
            '<p class="form-hint">Supported: LinkedIn and Naukri job ' +
            'postings.</p>' +
          '</div>' +
          '<button class="btn" type="submit">Scrape job description</button>' +
        '</form>' +
      '</div>' +
      '<div id="jd-result"></div>'
    );
  }

  function skillList(skills) {
    if (!skills || !skills.length) {
      return '<p class="muted">None listed.</p>';
    }
    return (
      '<div class="chip-row">' +
      skills
        .map(function (s) {
          return '<span class="chip">' + UI.escape(s) + '</span>';
        })
        .join('') +
      '</div>'
    );
  }

  function techStackSection(techStack) {
    if (!techStack) return '';

    // Informational message when nothing could be extracted (Req 2.3).
    const hasItems = (techStack.items || []).length > 0;
    if (!hasItems) {
      const msg =
        techStack.message ||
        'No specific tech stack could be identified. Please review the ' +
          'posting manually.';
      return (
        '<div class="card">' +
          '<div class="card-header"><h2>Tech stack</h2></div>' +
          '<p class="muted">' + UI.escape(msg) + '</p>' +
        '</div>'
      );
    }

    function renderItems(items) {
      if (!items || !items.length) {
        return '<p class="muted">None.</p>';
      }
      return (
        '<div class="chip-row">' +
        items
          .map(function (it) {
            const cat = CATEGORY_LABELS[it.category] || it.category || '';
            return (
              '<span class="chip chip-tech" title="' + UI.escape(cat) + '">' +
                UI.escape(it.name) +
                (cat ? ' <span class="chip-meta">' + UI.escape(cat) + '</span>' : '') +
              '</span>'
            );
          })
          .join('') +
        '</div>'
      );
    }

    return (
      '<div class="card">' +
        '<div class="card-header"><h2>Tech stack</h2></div>' +
        '<div class="split-cols">' +
          '<div>' +
            '<h3 class="subhead">' +
              'Required <span class="badge badge-danger">' +
              (techStack.required || []).length + '</span>' +
            '</h3>' +
            renderItems(techStack.required) +
          '</div>' +
          '<div>' +
            '<h3 class="subhead">' +
              'Nice-to-have <span class="badge badge-neutral">' +
              (techStack.nice_to_have || []).length + '</span>' +
            '</h3>' +
            renderItems(techStack.nice_to_have) +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  function confirmationView(jd, pretty, techStack) {
    return (
      '<div class="card">' +
        '<div class="card-header">' +
          '<h2>Scraped job description</h2>' +
          '<span class="badge badge-success">Ready to confirm</span>' +
        '</div>' +
        '<div class="jd-grid">' +
          '<div class="jd-field"><span class="jd-label">Title</span>' +
            '<span class="jd-value">' + UI.escape(jd.job_title) + '</span></div>' +
          '<div class="jd-field"><span class="jd-label">Company</span>' +
            '<span class="jd-value">' + UI.escape(jd.company_name) + '</span></div>' +
          '<div class="jd-field"><span class="jd-label">Location</span>' +
            '<span class="jd-value">' + UI.escape(jd.location || '—') + '</span></div>' +
          '<div class="jd-field"><span class="jd-label">Experience</span>' +
            '<span class="jd-value">' + UI.escape(jd.experience_required || '—') + '</span></div>' +
        '</div>' +
        '<h3 class="subhead">Required skills</h3>' +
        skillList(jd.required_skills) +
        '<h3 class="subhead">Preferred skills</h3>' +
        skillList(jd.preferred_skills) +
        '<h3 class="subhead">Description</h3>' +
        '<pre class="jd-pretty">' + UI.escape(pretty || jd.description_body || '') + '</pre>' +
        '<div class="btn-row">' +
          '<button class="btn" id="jd-continue" type="button">Confirm &amp; match my resume</button>' +
          '<button class="btn btn-secondary" id="jd-scrape-another" type="button">Scrape another</button>' +
        '</div>' +
      '</div>' +
      techStackSection(techStack)
    );
  }

  function showFormError(message) {
    const el = document.getElementById('jd-error');
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
  }

  function clearFormError() {
    const el = document.getElementById('jd-error');
    if (el) el.hidden = true;
  }

  function setSubmitting(form, submitting) {
    const btn = form.querySelector('button[type="submit"]');
    if (!btn) return;
    btn.disabled = submitting;
    btn.innerHTML = submitting
      ? '<span class="spinner"></span> Scraping...'
      : 'Scrape job description';
  }

  function renderResult(jd, pretty, techStack) {
    const result = document.getElementById('jd-result');
    if (!result) return;
    result.innerHTML = confirmationView(jd, pretty, techStack);

    const continueBtn = document.getElementById('jd-continue');
    if (continueBtn) {
      continueBtn.addEventListener('click', function () {
        Router.navigate('/match?jd=' + encodeURIComponent(jd.id));
      });
    }

    const anotherBtn = document.getElementById('jd-scrape-another');
    if (anotherBtn) {
      anotherBtn.addEventListener('click', function () {
        result.innerHTML = '';
        const input = document.getElementById('jd-url');
        if (input) {
          input.value = '';
          input.focus();
        }
      });
    }
  }

  function render(view) {
    view.innerHTML = header() + formCard();

    const form = document.getElementById('jd-form');
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      clearFormError();

      const url = form.url.value.trim();
      if (!url) {
        showFormError('Please enter a job posting URL.');
        return;
      }

      setSubmitting(form, true);
      try {
        const res = await Api.post('/api/jd/scrape', { body: { url: url } });
        // Remember this JD as the active one for downstream pages.
        Store.setSelectedJd(res.jd);
        UI.toast('Job description scraped successfully.', 'success');
        renderResult(res.jd, res.pretty, res.tech_stack);
      } catch (err) {
        // Unsupported URL (400) and fetch failures (502) both arrive as
        // ApiError with a descriptive backend message (Req 1.3, 1.4).
        const message =
          err instanceof ApiError
            ? err.message
            : 'Something went wrong while scraping. Please try again.';
        showFormError(message);
      } finally {
        setSubmitting(form, false);
      }
    });
  }

  App.registerRoute('/jd', {
    requiresAuth: true,
    title: 'Scrape JD',
    render: render,
  });
})(window.App);
