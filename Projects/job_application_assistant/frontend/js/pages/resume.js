/* =========================================================================
   Resume page (js/pages/resume.js)

   Route: #/resume

   Lets the user upload (or replace) their single base resume and view the
   currently stored resume's details:
     * file upload form accepting PDF/DOCX — Requirements 3.1, 3.7
     * current resume details: file name, upload date, extracted skills
       summary — Requirements 3.5, 3.6
     * re-uploading replaces the stored resume — Requirement 3.2
     * unsupported formats surface an inline validation error — Requirement 3.7

   On load it GETs the stored resume (404 simply means "none yet"). After a
   successful upload it re-renders the stored details from the upload response.

   Registers the /resume route, overriding the placeholder stub (loaded after
   placeholders.js in index.html).
   ========================================================================= */
(function (App) {
  'use strict';

  const UI = App.UI;
  const Api = App.Api;
  const ApiError = App.ApiError;

  //: Client-side allow-list mirrors the backend's accepted extensions.
  const ACCEPTED_EXTENSIONS = ['.pdf', '.docx'];

  function header() {
    return (
      '<div class="page-header">' +
        '<h1 class="page-title">My Resume</h1>' +
        '<p class="page-subtitle">Upload your base resume once — it is reused ' +
        'for every job you analyze.</p>' +
      '</div>'
    );
  }

  function formatDate(value) {
    if (!value) return '—';
    // The backend stores timezone-naive UTC timestamps, so the ISO string
    // may arrive without a timezone designator (e.g. "2026-11-10T09:30:00").
    // JavaScript would otherwise parse such a string as LOCAL time, shifting
    // the displayed value by the browser's UTC offset. Normalise to UTC by
    // appending "Z" when no timezone/offset is present.
    let normalized = value;
    if (typeof value === 'string') {
      const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(value);
      if (!hasTz) {
        normalized = value.replace(' ', 'T') + 'Z';
      }
    }
    const d = new Date(normalized);
    if (isNaN(d.getTime())) return UI.escape(value);
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  function warningBanner(warning) {
    if (!warning) return '';
    return (
      '<div class="alert alert-warning" role="alert" ' +
        'style="margin-bottom:12px;padding:12px 14px;border-radius:8px;' +
        'background:#fff8e6;border:1px solid #f0d98a;color:#7a5b00;">' +
        '<strong>⚠️ Heads up:</strong> ' + UI.escape(warning) +
      '</div>'
    );
  }

  function skillsSummary(skills) {
    if (!skills || !skills.length) {
      return '<p class="muted">No skills were extracted from this resume.</p>';
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

  function currentResumeCard(resume) {
    if (!resume) {
      return (
        '<div class="card">' +
          '<div class="card-header"><h2>Current resume</h2></div>' +
          '<div class="empty-state">' +
            '<div class="empty-icon">📄</div>' +
            '<h2>No resume uploaded yet</h2>' +
            '<p class="muted">Upload a PDF or Word document to get started.</p>' +
          '</div>' +
        '</div>'
      );
    }

    return (
      '<div class="card">' +
        '<div class="card-header">' +
          '<h2>Current resume</h2>' +
          '<span class="badge badge-primary">' +
            UI.escape((resume.file_type || '').toUpperCase()) +
          '</span>' +
        '</div>' +
        '<div class="jd-grid">' +
          '<div class="jd-field"><span class="jd-label">File name</span>' +
            '<span class="jd-value">' + UI.escape(resume.file_name) + '</span></div>' +
          '<div class="jd-field"><span class="jd-label">Uploaded</span>' +
            '<span class="jd-value">' + formatDate(resume.uploaded_at) + '</span></div>' +
        '</div>' +
        warningBanner(resume.warning) +
        '<h3 class="subhead">Extracted skills</h3>' +
        skillsSummary(resume.skills) +
      '</div>'
    );
  }

  function uploadCard(hasResume) {
    return (
      '<div class="card">' +
        '<div class="card-header">' +
          '<h2>' + (hasResume ? 'Replace resume' : 'Upload resume') + '</h2>' +
        '</div>' +
        '<form id="resume-form" novalidate>' +
          '<div id="resume-error" class="form-error" hidden></div>' +
          '<div class="form-group">' +
            '<label class="form-label" for="resume-file">Resume file</label>' +
            '<input class="form-control" id="resume-file" name="file" type="file" ' +
              'accept=".pdf,.docx" required />' +
            '<p class="form-hint">Accepted formats: PDF (.pdf) and Word (.docx).' +
            (hasResume ? ' Uploading replaces your current resume.' : '') +
            '</p>' +
          '</div>' +
          '<button class="btn" type="submit">' +
            (hasResume ? 'Replace resume' : 'Upload resume') +
          '</button>' +
        '</form>' +
      '</div>'
    );
  }

  function showError(message) {
    const el = document.getElementById('resume-error');
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
  }

  function clearError() {
    const el = document.getElementById('resume-error');
    if (el) el.hidden = true;
  }

  function setSubmitting(form, submitting, label) {
    const btn = form.querySelector('button[type="submit"]');
    if (!btn) return;
    btn.disabled = submitting;
    btn.innerHTML = submitting
      ? '<span class="spinner"></span> Uploading...'
      : UI.escape(label);
  }

  function hasAcceptedExtension(fileName) {
    const lower = (fileName || '').toLowerCase();
    return ACCEPTED_EXTENSIONS.some(function (ext) {
      return lower.endsWith(ext);
    });
  }

  function bindForm(view) {
    const form = document.getElementById('resume-form');
    if (!form) return;
    const hadResume = !!view.querySelector('.badge-primary');
    const idleLabel = hadResume ? 'Replace resume' : 'Upload resume';

    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      clearError();

      const input = form.file;
      const file = input && input.files && input.files[0];
      if (!file) {
        showError('Please choose a resume file to upload.');
        return;
      }

      // Client-side format validation (Req 3.7) before hitting the network.
      if (!hasAcceptedExtension(file.name)) {
        showError(
          'Unsupported file type. Supported formats are PDF (.pdf) and ' +
            'Word (.docx).'
        );
        return;
      }

      const data = new FormData();
      data.append('file', file);

      setSubmitting(form, true, idleLabel);
      try {
        const res = await Api.post('/api/resume/upload', { body: data });
        const parsed = res.parsed || {};
        const warning = parsed.warning || null;
        if (warning) {
          UI.toast('Resume uploaded, but some details could not be extracted.', 'warning');
        } else {
          UI.toast('Resume uploaded successfully.', 'success');
        }
        // Re-render from the upload response (details + parsed skills).
        renderStored(view, {
          id: res.id,
          file_name: res.file_name,
          file_type: res.file_type,
          uploaded_at: res.uploaded_at,
          skills: parsed.skills || [],
          warning: warning,
        });
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.message
            : 'Something went wrong while uploading. Please try again.';
        showError(message);
        setSubmitting(form, false, idleLabel);
      }
    });
  }

  function renderStored(view, resume) {
    view.innerHTML =
      header() + currentResumeCard(resume) + uploadCard(!!resume);
    bindForm(view);
  }

  async function render(view) {
    view.innerHTML = header() + UI.renderLoading('Loading your resume...');

    let resume = null;
    try {
      resume = await Api.get('/api/resume');
    } catch (err) {
      // 404 => no resume uploaded yet; anything else is a real error.
      if (!(err instanceof ApiError) || err.status !== 404) {
        throw err;
      }
    }

    renderStored(view, resume);
  }

  App.registerRoute('/resume', {
    requiresAuth: true,
    title: 'My Resume',
    render: render,
  });
})(window.App);
