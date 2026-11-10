/* =========================================================================
   Cover letter page (js/pages/cover_letter.js)

   Route: #/cover-letter   (optional ?jd=<jd_id> to target a specific JD)

   Generates a tailored cover letter for the selected JD and lets the user
   review/edit it before downloading:
     * generation trigger that produces a structured cover letter from the
       user's base resume and the JD — Requirements 10.1, 10.2
     * an experience-level selector that tailors tone and depth
       — Requirement 10.3
     * the generated content shown in an editable text area for review and
       manual edits — Requirement 10.4
     * a download button for the .docx — Requirements 10.5, 10.6

   The target JD comes from the ?jd query param or the remembered "selected
   JD" (App.Store). When no JD exists the page prompts the user to scrape a
   JD first; when no resume is uploaded the backend returns 400 and the page
   routes the user to upload one.

   Note: downloading returns the .docx of the last *generated* letter. Manual
   edits in the text area are for the user's own review/copy; regenerate to
   change the downloadable document.

   Registers the /cover-letter route, overriding the placeholder stub (loaded
   after placeholders.js in index.html).
   ========================================================================= */
(function (App) {
  'use strict';

  const UI = App.UI;
  const Api = App.Api;
  const Store = App.Store;
  const Router = App.Router;
  const ApiError = App.ApiError;

  // Experience levels offered by the selector (value + display label).
  const EXPERIENCE_LEVELS = [
    ['', 'Use my profile default'],
    ['Fresher', 'Fresher'],
    ['Junior', 'Junior'],
    ['Mid-Level', 'Mid-Level'],
    ['Senior', 'Senior'],
    ['Lead/Architect', 'Lead / Architect'],
  ];

  // Page-local state for the current render.
  let state = {
    jdId: null,
    jd: null,
    content: '',
    generated: false,
    experienceLevel: '',
  };

  function header(jd) {
    const subtitle = jd
      ? UI.escape(jd.job_title) +
        (jd.company_name ? ' · ' + UI.escape(jd.company_name) : '')
      : 'Generate a tailored cover letter for each application.';
    return (
      '<div class="page-header">' +
        '<h1 class="page-title">Cover Letter</h1>' +
        '<p class="page-subtitle">' + subtitle + '</p>' +
      '</div>'
    );
  }

  function noJdView(view) {
    view.innerHTML =
      header(null) +
      '<div class="card"><div class="empty-state">' +
        '<div class="empty-icon">✉️</div>' +
        '<h2>No job selected</h2>' +
        '<p class="muted">Scrape a job description first, then come back to ' +
        'generate a cover letter.</p>' +
        '<div class="btn-row" style="justify-content:center">' +
          '<button class="btn" id="go-scrape" type="button">Scrape a JD</button>' +
        '</div>' +
      '</div></div>';
    const btn = document.getElementById('go-scrape');
    if (btn) {
      btn.addEventListener('click', function () {
        Router.navigate('/jd');
      });
    }
  }

  function experienceOptions(selected) {
    return EXPERIENCE_LEVELS.map(function (pair) {
      const value = pair[0];
      const label = pair[1];
      const sel = value === selected ? ' selected' : '';
      return '<option value="' + UI.escape(value) + '"' + sel + '>' +
        UI.escape(label) + '</option>';
    }).join('');
  }

  function controlsCard() {
    return (
      '<div class="card">' +
        '<div class="card-header"><h2>Generate cover letter</h2></div>' +
        '<div id="cl-action-error" class="form-error" hidden></div>' +
        '<p class="muted">Creates a cover letter tailored to this job using ' +
        'your uploaded resume. You can review and edit it below before ' +
        'downloading.</p>' +
        '<div class="form-group" style="max-width:320px">' +
          '<label class="form-label" for="cl-exp-level">Experience level</label>' +
          '<select class="form-control" id="cl-exp-level">' +
            experienceOptions(state.experienceLevel) +
          '</select>' +
          '<p class="form-hint">Adjusts the tone and depth of the letter.</p>' +
        '</div>' +
        '<div class="btn-row">' +
          '<button class="btn" id="gen-cl" type="button">' +
            (state.generated ? 'Regenerate' : 'Generate cover letter') +
          '</button>' +
        '</div>' +
      '</div>'
    );
  }

  function editorCard() {
    if (!state.generated) {
      return (
        '<div class="card">' +
          '<div class="card-header"><h2>Cover letter</h2></div>' +
          '<p class="muted">Generate a cover letter to review and edit it ' +
          'here.</p>' +
        '</div>'
      );
    }
    return (
      '<div class="card">' +
        '<div class="card-header">' +
          '<h2>Review &amp; edit</h2>' +
          '<span class="badge badge-success">Generated</span>' +
        '</div>' +
        '<div class="form-group">' +
          '<label class="form-label" for="cl-content">Cover letter content</label>' +
          '<textarea class="form-control cl-textarea" id="cl-content" ' +
            'spellcheck="true">' + UI.escape(state.content) + '</textarea>' +
          '<p class="form-hint">Edit freely for your own copy. The download ' +
          'contains the last generated version — regenerate to change the ' +
          'downloadable document.</p>' +
        '</div>' +
        '<div class="btn-row">' +
          '<button class="btn btn-secondary" id="dl-cl" type="button">' +
            'Download .docx</button>' +
        '</div>' +
      '</div>'
    );
  }

  function showActionError(message) {
    const el = document.getElementById('cl-action-error');
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
  }

  function clearActionError() {
    const el = document.getElementById('cl-action-error');
    if (el) el.hidden = true;
  }

  function renderBody(view) {
    view.innerHTML = header(state.jd) + controlsCard() + editorCard();
    bindControls(view);
  }

  function bindControls(view) {
    const select = view.querySelector('#cl-exp-level');
    if (select) {
      select.addEventListener('change', function () {
        state.experienceLevel = select.value;
      });
    }

    const genBtn = view.querySelector('#gen-cl');
    if (genBtn) {
      genBtn.addEventListener('click', function () {
        generate(view);
      });
    }

    const textarea = view.querySelector('#cl-content');
    if (textarea) {
      // Keep local state in sync so a re-render preserves manual edits.
      textarea.addEventListener('input', function () {
        state.content = textarea.value;
      });
    }

    const dlBtn = view.querySelector('#dl-cl');
    if (dlBtn) {
      dlBtn.addEventListener('click', function () {
        download(dlBtn);
      });
    }
  }

  async function generate(view) {
    clearActionError();
    const genBtn = view.querySelector('#gen-cl');
    const original = genBtn ? genBtn.innerHTML : '';
    if (genBtn) {
      genBtn.disabled = true;
      genBtn.innerHTML = '<span class="spinner"></span> Generating...';
    }

    try {
      const body = state.experienceLevel
        ? { experience_level: state.experienceLevel }
        : undefined;
      const res = await Api.post(
        '/api/cover-letter/' + encodeURIComponent(state.jdId),
        body ? { body: body } : undefined
      );
      state.content = (res && res.content) || '';
      state.generated = true;
      UI.toast('Cover letter generated.', 'success');
      renderBody(view);
    } catch (err) {
      // 400 most commonly means no resume uploaded yet.
      if (err instanceof ApiError && err.status === 400) {
        view.innerHTML =
          header(state.jd) +
          '<div class="card"><div class="empty-state">' +
            '<div class="empty-icon">📄</div>' +
            '<h2>Upload a resume first</h2>' +
            '<p class="muted">' + UI.escape(err.message) + '</p>' +
            '<div class="btn-row" style="justify-content:center">' +
              '<button class="btn" id="go-resume" type="button">Go to My Resume</button>' +
            '</div>' +
          '</div></div>';
        const btn = document.getElementById('go-resume');
        if (btn) {
          btn.addEventListener('click', function () {
            Router.navigate('/resume');
          });
        }
        return;
      }
      const message =
        err instanceof ApiError
          ? err.message
          : 'Failed to generate the cover letter. Please try again.';
      showActionError(message);
      if (genBtn) {
        genBtn.disabled = false;
        genBtn.innerHTML = original;
      }
    }
  }

  async function download(btn) {
    clearActionError();
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Preparing...';
    try {
      const res = await Api.get(
        '/api/cover-letter/' + encodeURIComponent(state.jdId) + '/download',
        { raw: true }
      );
      const blob = await res.blob();

      let filename = 'cover_letter.docx';
      const disposition = res.headers.get('Content-Disposition') || '';
      const match = /filename="?([^"]+)"?/i.exec(disposition);
      if (match && match[1]) filename = match[1];

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : 'Failed to download the cover letter.';
      showActionError(
        err instanceof ApiError && err.status === 404
          ? 'Generate the cover letter first, then download it.'
          : message
      );
    } finally {
      btn.disabled = false;
      btn.innerHTML = original;
    }
  }

  async function render(view, query) {
    const jdId = (query && query.jd) || (Store.getSelectedJd() || {}).id;
    if (!jdId) {
      noJdView(view);
      return;
    }

    const user = Store.getUser();
    state = {
      jdId: jdId,
      jd: null,
      content: '',
      generated: false,
      experienceLevel: (user && user.experience_level) || '',
    };

    // Resolve a display header from the cached selected JD, otherwise fetch.
    let jd = Store.getSelectedJd();
    if (!jd || jd.id !== jdId) {
      try {
        jd = await Api.get('/api/jd/' + encodeURIComponent(jdId));
        Store.setSelectedJd(jd);
      } catch (e) {
        jd = { id: jdId, job_title: 'Selected job', company_name: '' };
      }
    }
    state.jd = jd;

    renderBody(view);
  }

  App.registerRoute('/cover-letter', {
    requiresAuth: true,
    title: 'Cover Letter',
    render: render,
  });
})(window.App);
