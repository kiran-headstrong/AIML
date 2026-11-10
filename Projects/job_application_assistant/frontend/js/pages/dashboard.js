/* =========================================================================
   Job application tracking dashboard (js/pages/dashboard.js)

   Route: #/dashboard

   The command centre for managing a job search. It lists every analysed /
   tracked job in a table, surfaces summary statistics, and lets the user
   manage each entry inline:

     * Summary stats bar — total analysed, total applied, interviews
       scheduled, offers received (Requirements 9.9).
     * Tabular layout — job title, company, date analysed, match score,
       status, notes, deadline, and a link to the tailored resume
       (Requirements 9.1, 9.2).
     * Status dropdown — update the application status per entry
       (Requirement 9.3, 9.5).
     * Inline notes editing — add / edit free-text feedback per entry
       (Requirements 9.4, 9.5).
     * Deadline date picker — set / edit / clear a deadline, with a
       days-remaining indicator and an urgent highlight when within 2 days
       of a not-applied entry's deadline (Requirements 12.1-12.4).
     * Delete with confirmation — remove an entry and its associated data
       (Requirement 9.6).
     * Filter by status + sort controls (status / date / company / match
       score / deadline) (Requirements 9.8, 12.5).

   Data comes from GET /api/dashboard (filter/sort via query params) and
   GET /api/dashboard/summary. Mutations use PATCH and DELETE
   /api/dashboard/{entry_id}. A tailored resume, when present, is downloaded
   via GET /api/match/{jd_id}/download-resume.

   Registers the /dashboard route, overriding the placeholder stub (loaded
   after placeholders.js in index.html).
   ========================================================================= */
(function (App) {
  'use strict';

  const UI = App.UI;
  const Api = App.Api;
  const Router = App.Router;
  const ApiError = App.ApiError;

  // Human-readable labels + badge variants for each status value. The keys
  // mirror the backend JobStatus literal (schemas.py).
  const STATUS_META = {
    not_applied: { label: 'Not Applied', badge: 'badge-neutral' },
    applied: { label: 'Applied', badge: 'badge-primary' },
    interview_scheduled: { label: 'Interview Scheduled', badge: 'badge-warning' },
    interview_completed: { label: 'Interview Completed', badge: 'badge-warning' },
    offered: { label: 'Offered', badge: 'badge-success' },
    rejected: { label: 'Rejected', badge: 'badge-danger' },
  };
  const STATUS_ORDER = [
    'not_applied',
    'applied',
    'interview_scheduled',
    'interview_completed',
    'offered',
    'rejected',
  ];

  const SORT_OPTIONS = [
    ['date', 'Date analyzed (newest)'],
    ['status', 'Status'],
    ['company', 'Company (A–Z)'],
    ['match_score', 'Match score (highest)'],
    ['deadline', 'Deadline (soonest)'],
  ];

  // Page-local state. `entries`/`summary` hold the latest server data; the
  // filter/sort controls are mirrored here so re-fetches keep the selection.
  let state = {
    entries: [],
    summary: null,
    statusFilter: '', // '' == all
    sortBy: 'date',
  };

  // ---- Small helpers ----------------------------------------------------

  function round(n) {
    return Math.round((Number(n) || 0) * 10) / 10;
  }

  function formatDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }

  function statusLabel(status) {
    const meta = STATUS_META[status];
    return meta ? meta.label : status;
  }

  // ---- Header + summary -------------------------------------------------

  function header() {
    return (
      '<div class="page-header">' +
        '<h1 class="page-title">Dashboard</h1>' +
        '<p class="page-subtitle">Track all your analyzed and applied jobs ' +
        'in one place.</p>' +
      '</div>'
    );
  }

  function summaryBar(summary) {
    const s = summary || {
      total_analyzed: 0,
      total_applied: 0,
      interviews_scheduled: 0,
      offers_received: 0,
    };
    function card(value, label) {
      return (
        '<div class="stat-card">' +
          '<div class="stat-value">' + UI.escape(value) + '</div>' +
          '<div class="stat-label">' + UI.escape(label) + '</div>' +
        '</div>'
      );
    }
    return (
      '<div class="stat-grid">' +
        card(s.total_analyzed, 'Jobs analyzed') +
        card(s.total_applied, 'Applied') +
        card(s.interviews_scheduled, 'Interviews scheduled') +
        card(s.offers_received, 'Offers received') +
      '</div>'
    );
  }

  // ---- Filter / sort controls ------------------------------------------

  function controlsCard() {
    const statusOpts =
      '<option value=""' + (state.statusFilter === '' ? ' selected' : '') +
        '>All statuses</option>' +
      STATUS_ORDER.map(function (st) {
        const sel = state.statusFilter === st ? ' selected' : '';
        return '<option value="' + st + '"' + sel + '>' +
          UI.escape(STATUS_META[st].label) + '</option>';
      }).join('');

    const sortOpts = SORT_OPTIONS.map(function (opt) {
      const sel = state.sortBy === opt[0] ? ' selected' : '';
      return '<option value="' + opt[0] + '"' + sel + '>' +
        UI.escape(opt[1]) + '</option>';
    }).join('');

    return (
      '<div class="card">' +
        '<div class="dash-controls">' +
          '<div class="form-group dash-control">' +
            '<label class="form-label" for="dash-filter">Filter by status</label>' +
            '<select id="dash-filter" class="form-control">' + statusOpts +
            '</select>' +
          '</div>' +
          '<div class="form-group dash-control">' +
            '<label class="form-label" for="dash-sort">Sort by</label>' +
            '<select id="dash-sort" class="form-control">' + sortOpts +
            '</select>' +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  // ---- Table + rows -----------------------------------------------------

  function statusSelect(entry) {
    const opts = STATUS_ORDER.map(function (st) {
      const sel = entry.status === st ? ' selected' : '';
      return '<option value="' + st + '"' + sel + '>' +
        UI.escape(STATUS_META[st].label) + '</option>';
    }).join('');
    return (
      '<select class="form-control dash-status-select" ' +
        'data-id="' + UI.escape(entry.id) + '">' + opts + '</select>'
    );
  }

  function deadlineCell(entry) {
    const value = entry.deadline ? UI.escape(entry.deadline) : '';
    let indicator = '';
    if (entry.deadline && entry.days_remaining !== null &&
        entry.days_remaining !== undefined) {
      const days = entry.days_remaining;
      let text;
      if (days < 0) text = Math.abs(days) + 'd overdue';
      else if (days === 0) text = 'Due today';
      else text = days + 'd left';
      const badgeCls = entry.is_urgent ? 'badge-danger' : 'badge-neutral';
      indicator =
        '<span class="badge ' + badgeCls + ' dash-days">' +
          UI.escape(text) + '</span>';
    }
    return (
      '<div class="dash-deadline">' +
        '<input type="date" class="form-control dash-deadline-input" ' +
          'data-id="' + UI.escape(entry.id) + '" value="' + value + '" />' +
        (entry.deadline
          ? '<button type="button" class="btn btn-ghost btn-sm dash-deadline-clear" ' +
              'data-id="' + UI.escape(entry.id) + '" ' +
              'aria-label="Clear deadline" title="Clear deadline">✕</button>'
          : '') +
        indicator +
      '</div>'
    );
  }

  function notesCell(entry) {
    const notes = entry.notes || '';
    return (
      '<div class="dash-notes">' +
        '<textarea class="form-control dash-notes-input" rows="2" ' +
          'data-id="' + UI.escape(entry.id) + '" ' +
          'placeholder="Add feedback, recruiter contact, follow-ups...">' +
          UI.escape(notes) +
        '</textarea>' +
        '<button type="button" class="btn btn-secondary btn-sm dash-notes-save" ' +
          'data-id="' + UI.escape(entry.id) + '" disabled>Save</button>' +
      '</div>'
    );
  }

  function resumeCell(entry) {
    if (!entry.tailored_resume_id) {
      return '<span class="muted">—</span>';
    }
    return (
      '<button type="button" class="btn btn-ghost btn-sm dash-resume" ' +
        'data-jd="' + UI.escape(entry.jd_id) + '">Download</button>'
    );
  }

  function row(entry) {
    const score =
      entry.match_score !== null && entry.match_score !== undefined
        ? round(entry.match_score) + '%'
        : '—';
    const urgentCls = entry.is_urgent ? ' class="dash-row-urgent"' : '';
    return (
      '<tr' + urgentCls + ' data-id="' + UI.escape(entry.id) + '">' +
        '<td>' +
          '<div class="dash-title">' + UI.escape(entry.job_title) + '</div>' +
          '<div class="muted dash-company">' + UI.escape(entry.company_name) +
          '</div>' +
        '</td>' +
        '<td>' + UI.escape(formatDate(entry.created_at)) + '</td>' +
        '<td>' + score + '</td>' +
        '<td>' + statusSelect(entry) + '</td>' +
        '<td>' + notesCell(entry) + '</td>' +
        '<td>' + deadlineCell(entry) + '</td>' +
        '<td>' + resumeCell(entry) + '</td>' +
        '<td>' +
          '<button type="button" class="btn btn-danger btn-sm dash-delete" ' +
            'data-id="' + UI.escape(entry.id) + '">Delete</button>' +
        '</td>' +
      '</tr>'
    );
  }

  function tableCard() {
    if (!state.entries.length) {
      const msg = state.statusFilter
        ? 'No jobs match the selected status filter.'
        : 'You have not analyzed any jobs yet. Scrape a job description to ' +
          'get started.';
      return (
        '<div class="card"><div class="empty-state">' +
          '<div class="empty-icon">▣</div>' +
          '<h2>Nothing to show</h2>' +
          '<p class="muted">' + UI.escape(msg) + '</p>' +
          (state.statusFilter
            ? ''
            : '<div class="btn-row" style="justify-content:center">' +
                '<button class="btn" id="dash-go-scrape" type="button">' +
                'Scrape a JD</button></div>') +
        '</div></div>'
      );
    }

    const rows = state.entries.map(row).join('');
    return (
      '<div class="card">' +
        '<div class="table-wrap">' +
          '<table class="table dash-table">' +
            '<thead><tr>' +
              '<th>Job</th>' +
              '<th>Date</th>' +
              '<th>Match</th>' +
              '<th>Status</th>' +
              '<th>Notes</th>' +
              '<th>Deadline</th>' +
              '<th>Resume</th>' +
              '<th></th>' +
            '</tr></thead>' +
            '<tbody>' + rows + '</tbody>' +
          '</table>' +
        '</div>' +
      '</div>'
    );
  }

  // ---- Mutations --------------------------------------------------------

  /** Patch a single entry and refresh the summary bar afterwards. */
  async function patchEntry(entryId, body) {
    const updated = await Api.patch(
      '/api/dashboard/' + encodeURIComponent(entryId),
      { body: body }
    );
    // Replace the entry in local state so recomputed deadline fields show.
    const idx = state.entries.findIndex(function (e) {
      return e.id === entryId;
    });
    if (idx !== -1) state.entries[idx] = updated;
    return updated;
  }

  async function refreshSummary() {
    try {
      state.summary = await Api.get('/api/dashboard/summary');
      const bar = document.getElementById('dash-summary');
      if (bar) bar.outerHTML = '<div id="dash-summary">' +
        summaryBar(state.summary) + '</div>';
    } catch (e) {
      /* non-fatal: leave the existing bar in place */
    }
  }

  async function onStatusChange(select, view) {
    const entryId = select.getAttribute('data-id');
    const newStatus = select.value;
    select.disabled = true;
    try {
      await patchEntry(entryId, { status: newStatus });
      UI.toast('Status updated to "' + statusLabel(newStatus) + '".', 'success');
      // Status affects deadline urgency + the summary counts, so re-render
      // the affected row and refresh the summary bar.
      rerenderRow(entryId, view);
      await refreshSummary();
    } catch (err) {
      select.disabled = false;
      UI.toast(
        err instanceof ApiError ? err.message : 'Failed to update status.',
        'error'
      );
    }
  }

  async function onNotesSave(btn, view) {
    const entryId = btn.getAttribute('data-id');
    const textarea = view.querySelector(
      '.dash-notes-input[data-id="' + cssEscape(entryId) + '"]'
    );
    if (!textarea) return;
    btn.disabled = true;
    try {
      await patchEntry(entryId, { notes: textarea.value });
      UI.toast('Notes saved.', 'success');
      textarea.defaultValue = textarea.value; // mark as pristine
    } catch (err) {
      btn.disabled = false;
      UI.toast(
        err instanceof ApiError ? err.message : 'Failed to save notes.',
        'error'
      );
    }
  }

  async function onDeadlineChange(input, view) {
    const entryId = input.getAttribute('data-id');
    const value = input.value || null; // '' -> null clears the deadline
    input.disabled = true;
    try {
      await patchEntry(entryId, { deadline: value });
      UI.toast(value ? 'Deadline updated.' : 'Deadline cleared.', 'success');
      rerenderRow(entryId, view);
    } catch (err) {
      input.disabled = false;
      UI.toast(
        err instanceof ApiError ? err.message : 'Failed to update deadline.',
        'error'
      );
    }
  }

  async function onDeadlineClear(btn, view) {
    const entryId = btn.getAttribute('data-id');
    btn.disabled = true;
    try {
      await patchEntry(entryId, { deadline: null });
      UI.toast('Deadline cleared.', 'success');
      rerenderRow(entryId, view);
    } catch (err) {
      btn.disabled = false;
      UI.toast(
        err instanceof ApiError ? err.message : 'Failed to clear deadline.',
        'error'
      );
    }
  }

  async function onDelete(btn, view) {
    const entryId = btn.getAttribute('data-id');
    const entry = state.entries.find(function (e) { return e.id === entryId; });
    const label = entry ? entry.job_title : 'this job';
    const confirmed = window.confirm(
      'Delete "' + label + '" from your dashboard? This also removes its ' +
      'match results, interview prep, and generated documents. This cannot ' +
      'be undone.'
    );
    if (!confirmed) return;

    btn.disabled = true;
    try {
      await Api.del('/api/dashboard/' + encodeURIComponent(entryId));
      state.entries = state.entries.filter(function (e) {
        return e.id !== entryId;
      });
      UI.toast('Job entry deleted.', 'success');
      renderBody(view);
      await refreshSummary();
    } catch (err) {
      btn.disabled = false;
      UI.toast(
        err instanceof ApiError ? err.message : 'Failed to delete entry.',
        'error'
      );
    }
  }

  async function onResumeDownload(btn) {
    const jdId = btn.getAttribute('data-jd');
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Downloading...';
    try {
      const res = await Api.get(
        '/api/match/' + encodeURIComponent(jdId) + '/download-resume',
        { raw: true }
      );
      const blob = await res.blob();

      let filename = 'tailored_resume.docx';
      const disposition = res.headers.get('Content-Disposition') || '';
      const m = /filename="?([^"]+)"?/i.exec(disposition);
      if (m && m[1]) filename = m[1];

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      UI.toast(
        err instanceof ApiError ? err.message : 'Failed to download resume.',
        'error'
      );
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  }

  // ---- Re-rendering -----------------------------------------------------

  /** Replace a single row in the DOM from the latest state (post-PATCH). */
  function rerenderRow(entryId, view) {
    const entry = state.entries.find(function (e) { return e.id === entryId; });
    const tr = view.querySelector(
      'tr[data-id="' + cssEscape(entryId) + '"]'
    );
    if (!entry || !tr) return;
    tr.outerHTML = row(entry);
    // Re-bind handlers for the freshly inserted row's controls.
    bindRow(view.querySelector('tr[data-id="' + cssEscape(entryId) + '"]'), view);
  }

  // Minimal CSS attribute-value escaper for UUIDs used in selectors. UUIDs
  // only contain hex + hyphens so this is defensive; CSS.escape when present.
  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(value);
    }
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }

  function renderBody(view) {
    view.innerHTML =
      header() +
      '<div id="dash-summary">' + summaryBar(state.summary) + '</div>' +
      controlsCard() +
      tableCard();
    bindControls(view);
    bindRows(view);

    const scrapeBtn = view.querySelector('#dash-go-scrape');
    if (scrapeBtn) {
      scrapeBtn.addEventListener('click', function () {
        Router.navigate('/jd');
      });
    }
  }

  // ---- Event binding ----------------------------------------------------

  function bindControls(view) {
    const filter = view.querySelector('#dash-filter');
    if (filter) {
      filter.addEventListener('change', function () {
        state.statusFilter = filter.value;
        reload(view);
      });
    }
    const sort = view.querySelector('#dash-sort');
    if (sort) {
      sort.addEventListener('change', function () {
        state.sortBy = sort.value;
        reload(view);
      });
    }
  }

  function bindRow(tr, view) {
    if (!tr) return;

    const select = tr.querySelector('.dash-status-select');
    if (select) {
      select.addEventListener('change', function () {
        onStatusChange(select, view);
      });
    }

    const notesInput = tr.querySelector('.dash-notes-input');
    const notesSave = tr.querySelector('.dash-notes-save');
    if (notesInput && notesSave) {
      // Enable Save only when the text differs from the last saved value.
      notesInput.addEventListener('input', function () {
        notesSave.disabled = notesInput.value === notesInput.defaultValue;
      });
      notesSave.addEventListener('click', function () {
        onNotesSave(notesSave, view);
      });
    }

    const deadlineInput = tr.querySelector('.dash-deadline-input');
    if (deadlineInput) {
      deadlineInput.addEventListener('change', function () {
        onDeadlineChange(deadlineInput, view);
      });
    }
    const deadlineClear = tr.querySelector('.dash-deadline-clear');
    if (deadlineClear) {
      deadlineClear.addEventListener('click', function () {
        onDeadlineClear(deadlineClear, view);
      });
    }

    const resumeBtn = tr.querySelector('.dash-resume');
    if (resumeBtn) {
      resumeBtn.addEventListener('click', function () {
        onResumeDownload(resumeBtn);
      });
    }

    const deleteBtn = tr.querySelector('.dash-delete');
    if (deleteBtn) {
      deleteBtn.addEventListener('click', function () {
        onDelete(deleteBtn, view);
      });
    }
  }

  function bindRows(view) {
    view.querySelectorAll('tr[data-id]').forEach(function (tr) {
      bindRow(tr, view);
    });
  }

  // ---- Data loading -----------------------------------------------------

  /** Re-fetch entries for the current filter/sort and re-render the table. */
  async function reload(view) {
    const query = { sort_by: state.sortBy };
    if (state.statusFilter) query.status_filter = state.statusFilter;
    try {
      const data = await Api.get('/api/dashboard', { query: query });
      state.entries = (data && data.entries) || [];
      renderBody(view);
    } catch (err) {
      UI.toast(
        err instanceof ApiError ? err.message : 'Failed to load dashboard.',
        'error'
      );
    }
  }

  async function render(view) {
    state = { entries: [], summary: null, statusFilter: '', sortBy: 'date' };
    view.innerHTML = header() + UI.renderLoading('Loading your dashboard...');

    // Fetch entries and summary together; both are needed for the first paint.
    const [data, summary] = await Promise.all([
      Api.get('/api/dashboard', { query: { sort_by: state.sortBy } }),
      Api.get('/api/dashboard/summary'),
    ]);

    state.entries = (data && data.entries) || [];
    state.summary = summary;
    renderBody(view);
  }

  App.registerRoute('/dashboard', {
    requiresAuth: true,
    title: 'Dashboard',
    render: render,
  });
})(window.App);
