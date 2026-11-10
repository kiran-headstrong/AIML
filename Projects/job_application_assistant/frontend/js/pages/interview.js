/* =========================================================================
   Interview preparation page (js/pages/interview.js)

   Route: #/interview   (optional ?jd=<jd_id> to target a specific JD)

   Generates and displays interview preparation material for the selected JD:
     * ranked topics grouped by category (Technical / Domain / Behavioral),
       most relevant first — Requirements 7.1, 7.2, 7.3
     * Q&A sets with difficulty filters (Easy / Medium / Difficult),
       scenario-based question indicators, model answers, and highlighted
       key points — Requirements 8.1, 8.2, 8.3, 8.5, 8.6
     * an experience-level selector that re-generates tailored Q&A
       — Requirement 8.4
     * a PDF export download button — Requirements 14.1, 14.2, 14.3, 14.4

   The target JD comes from the ?jd query param or the remembered "selected
   JD" (App.Store). Topics are generated first, then Q&A are generated (the
   backend auto-generates topics if needed). When no JD exists the page
   prompts the user to scrape a JD first.

   Registers the /interview route, overriding the placeholder stub (loaded
   after placeholders.js in index.html).
   ========================================================================= */
(function (App) {
  'use strict';

  const UI = App.UI;
  const Api = App.Api;
  const Store = App.Store;
  const Router = App.Router;
  const ApiError = App.ApiError;

  // Ordering + labels for topic categories.
  const TOPIC_CATEGORIES = [
    ['technical', 'Technical Topics'],
    ['domain', 'Domain Knowledge Topics'],
    ['behavioral', 'Behavioral / Soft Skills Topics'],
  ];
  const TOPIC_BADGE = {
    technical: 'badge-primary',
    domain: 'badge-warning',
    behavioral: 'badge-success',
  };

  // Ordering + labels/badges for difficulty tiers.
  const DIFFICULTY_ORDER = { easy: 0, medium: 1, difficult: 2 };
  const DIFFICULTY_LABEL = { easy: 'Easy', medium: 'Medium', difficult: 'Difficult' };
  const DIFFICULTY_BADGE = {
    easy: 'badge-success',
    medium: 'badge-warning',
    difficult: 'badge-danger',
  };

  // Experience levels offered by the selector (value + display label).
  const EXPERIENCE_LEVELS = [
    ['', 'Use my profile default'],
    ['Fresher', 'Fresher'],
    ['Junior', 'Junior'],
    ['Mid-Level', 'Mid-Level'],
    ['Senior', 'Senior'],
    ['Lead/Architect', 'Lead / Architect'],
  ];

  // Page-local state for the current render (JD + generated material).
  let state = {
    jdId: null,
    jd: null,
    topics: [],
    qa: [],
    experienceLevel: '',
    activeDifficulty: 'all',
  };

  function header(jd) {
    const subtitle = jd
      ? UI.escape(jd.job_title) +
        (jd.company_name ? ' · ' + UI.escape(jd.company_name) : '')
      : 'Generate topics and Q&A tailored to the role.';
    return (
      '<div class="page-header">' +
        '<h1 class="page-title">Interview Prep</h1>' +
        '<p class="page-subtitle">' + subtitle + '</p>' +
      '</div>'
    );
  }

  function noJdView(view) {
    view.innerHTML =
      header(null) +
      '<div class="card"><div class="empty-state">' +
        '<div class="empty-icon">🎤</div>' +
        '<h2>No job selected</h2>' +
        '<p class="muted">Scrape a job description first, then come back to ' +
        'prepare for the interview.</p>' +
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

  // ---- Controls card: experience selector, generate + export buttons ----

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
    const hasMaterial = state.topics.length > 0 || state.qa.length > 0;
    return (
      '<div class="card">' +
        '<div class="card-header"><h2>Preparation controls</h2></div>' +
        '<div id="interview-action-error" class="form-error" hidden></div>' +
        '<div class="form-group" style="max-width:320px">' +
          '<label class="form-label" for="exp-level">Experience level</label>' +
          '<select class="form-control" id="exp-level">' +
            experienceOptions(state.experienceLevel) +
          '</select>' +
          '<p class="form-hint">Tailors the depth and complexity of the ' +
          'generated questions.</p>' +
        '</div>' +
        '<div class="btn-row">' +
          '<button class="btn" id="gen-prep" type="button">' +
            (hasMaterial ? 'Regenerate prep' : 'Generate prep') +
          '</button>' +
          '<button class="btn btn-secondary" id="export-pdf" type="button"' +
            (hasMaterial ? '' : ' disabled') + '>Export as PDF</button>' +
        '</div>' +
      '</div>'
    );
  }

  // ---- Topics card: grouped by category, ranked by relevance -----------

  function topicsCard() {
    if (!state.topics.length) {
      return (
        '<div class="card">' +
          '<div class="card-header"><h2>Topics</h2></div>' +
          '<p class="muted">Generate prep to see ranked interview topics.</p>' +
        '</div>'
      );
    }

    let body = '';
    TOPIC_CATEGORIES.forEach(function (pair) {
      const key = pair[0];
      const label = pair[1];
      const group = state.topics
        .filter(function (t) {
          return t.category === key;
        })
        .sort(function (a, b) {
          return (a.relevance_rank || 0) - (b.relevance_rank || 0);
        });
      if (!group.length) return;

      const badge = TOPIC_BADGE[key] || 'badge-neutral';
      body +=
        '<h3 class="subhead">' + UI.escape(label) + '</h3>' +
        '<ol class="topic-list">' +
        group
          .map(function (t) {
            return (
              '<li class="topic-item">' +
                '<span class="badge ' + badge + '">#' +
                  UI.escape(String(t.relevance_rank)) + '</span>' +
                '<span class="topic-name">' + UI.escape(t.name) + '</span>' +
              '</li>'
            );
          })
          .join('') +
        '</ol>';
    });

    return (
      '<div class="card">' +
        '<div class="card-header"><h2>Topics</h2></div>' +
        body +
      '</div>'
    );
  }

  // ---- Q&A card: difficulty filters + grouped questions ----------------

  function difficultyFilters() {
    const counts = { all: state.qa.length, easy: 0, medium: 0, difficult: 0 };
    state.qa.forEach(function (q) {
      if (counts[q.difficulty] !== undefined) counts[q.difficulty] += 1;
    });

    const tabs = [
      ['all', 'All'],
      ['easy', DIFFICULTY_LABEL.easy],
      ['medium', DIFFICULTY_LABEL.medium],
      ['difficult', DIFFICULTY_LABEL.difficult],
    ];

    return (
      '<div class="filter-tabs" id="difficulty-filters">' +
      tabs
        .map(function (pair) {
          const value = pair[0];
          const label = pair[1];
          const active = value === state.activeDifficulty ? ' active' : '';
          return (
            '<button class="filter-tab' + active + '" type="button" ' +
              'data-difficulty="' + value + '">' +
              UI.escape(label) +
              ' <span class="filter-count">' + counts[value] + '</span>' +
            '</button>'
          );
        })
        .join('') +
      '</div>'
    );
  }

  function qaItem(q) {
    const badge = DIFFICULTY_BADGE[q.difficulty] || 'badge-neutral';
    const scenario = q.is_scenario_based
      ? '<span class="badge badge-primary">Scenario</span>'
      : '';
    const keyPoints =
      q.key_points && q.key_points.length
        ? '<div class="qa-keypoints">' +
          '<span class="qa-keypoints-label">Key points</span>' +
          '<ul>' +
          q.key_points
            .map(function (kp) {
              return '<li>' + UI.escape(kp) + '</li>';
            })
            .join('') +
          '</ul></div>'
        : '';

    return (
      '<li class="qa-item" data-difficulty="' + UI.escape(q.difficulty) + '">' +
        '<div class="qa-head">' +
          '<span class="badge ' + badge + '">' +
            UI.escape(DIFFICULTY_LABEL[q.difficulty] || q.difficulty) + '</span>' +
          scenario +
          (q.topic ? '<span class="qa-topic">' + UI.escape(q.topic) + '</span>' : '') +
        '</div>' +
        '<p class="qa-question">' + UI.escape(q.question) + '</p>' +
        '<div class="qa-answer">' +
          '<span class="qa-answer-label">Model answer</span>' +
          '<p>' + UI.escape(q.answer) + '</p>' +
        '</div>' +
        keyPoints +
      '</li>'
    );
  }

  function qaCard() {
    if (!state.qa.length) {
      return (
        '<div class="card">' +
          '<div class="card-header"><h2>Questions &amp; Answers</h2></div>' +
          '<p class="muted">Generate prep to see tailored interview ' +
          'questions with model answers.</p>' +
        '</div>'
      );
    }

    // Order by difficulty tier, then keep scenario-based grouping stable.
    const ordered = state.qa.slice().sort(function (a, b) {
      return (
        (DIFFICULTY_ORDER[a.difficulty] ?? 3) -
        (DIFFICULTY_ORDER[b.difficulty] ?? 3)
      );
    });

    const visible =
      state.activeDifficulty === 'all'
        ? ordered
        : ordered.filter(function (q) {
            return q.difficulty === state.activeDifficulty;
          });

    const list = visible.length
      ? '<ul class="qa-list">' + visible.map(qaItem).join('') + '</ul>'
      : '<p class="muted">No questions in this difficulty tier.</p>';

    return (
      '<div class="card">' +
        '<div class="card-header"><h2>Questions &amp; Answers</h2></div>' +
        difficultyFilters() +
        list +
      '</div>'
    );
  }

  // ---- Error helpers ---------------------------------------------------

  function showActionError(message) {
    const el = document.getElementById('interview-action-error');
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
  }

  function clearActionError() {
    const el = document.getElementById('interview-action-error');
    if (el) el.hidden = true;
  }

  // ---- Rendering + binding ---------------------------------------------

  function renderBody(view) {
    view.innerHTML =
      header(state.jd) +
      controlsCard() +
      topicsCard() +
      qaCard();
    bindControls(view);
    bindDifficultyFilters(view);
  }

  function bindDifficultyFilters(view) {
    const container = view.querySelector('#difficulty-filters');
    if (!container) return;
    container.addEventListener('click', function (e) {
      const btn = e.target.closest('.filter-tab');
      if (!btn) return;
      state.activeDifficulty = btn.getAttribute('data-difficulty') || 'all';
      renderBody(view);
    });
  }

  function bindControls(view) {
    const select = view.querySelector('#exp-level');
    if (select) {
      select.addEventListener('change', function () {
        state.experienceLevel = select.value;
      });
    }

    const genBtn = view.querySelector('#gen-prep');
    if (genBtn) {
      genBtn.addEventListener('click', function () {
        generatePrep(view);
      });
    }

    const exportBtn = view.querySelector('#export-pdf');
    if (exportBtn) {
      exportBtn.addEventListener('click', function () {
        exportPdf(exportBtn);
      });
    }
  }

  /**
   * Generate topics then Q&A for the current JD, tailored to the selected
   * experience level, and re-render. The Q&A endpoint auto-generates topics
   * when absent; we still call topics first so the ranked list is persisted
   * and returned explicitly.
   */
  async function generatePrep(view) {
    clearActionError();
    const genBtn = view.querySelector('#gen-prep');
    const original = genBtn ? genBtn.innerHTML : '';
    if (genBtn) {
      genBtn.disabled = true;
      genBtn.innerHTML = '<span class="spinner"></span> Generating...';
    }

    try {
      const base = '/api/interview/' + encodeURIComponent(state.jdId);
      // Generate ranked topics first (Requirements 7.1-7.3).
      const topicsRes = await Api.post(base + '/topics');
      // Then generate Q&A tailored to the selected experience level.
      const body = state.experienceLevel
        ? { experience_level: state.experienceLevel }
        : undefined;
      const qaRes = await Api.post(base + '/qa', body ? { body: body } : undefined);

      state.topics = (qaRes && qaRes.topics && qaRes.topics.length
        ? qaRes.topics
        : (topicsRes && topicsRes.topics) || []);
      state.qa = (qaRes && qaRes.qa) || [];
      state.activeDifficulty = 'all';

      UI.toast('Interview prep generated.', 'success');
      renderBody(view);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : 'Failed to generate interview prep. Please try again.';
      showActionError(message);
      if (genBtn) {
        genBtn.disabled = false;
        genBtn.innerHTML = original;
      }
    }
  }

  async function exportPdf(btn) {
    clearActionError();
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Preparing...';
    try {
      const res = await Api.get(
        '/api/interview/' + encodeURIComponent(state.jdId) + '/export-pdf',
        { raw: true }
      );
      const blob = await res.blob();

      let filename = 'interview_prep.pdf';
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
          : 'Failed to export the interview prep PDF.';
      showActionError(
        err instanceof ApiError && err.status === 404
          ? 'Generate interview prep first, then export it.'
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

    // Reset page state for this JD (fresh visit — material is generated on
    // demand via the controls rather than auto-loaded).
    const user = Store.getUser();
    state = {
      jdId: jdId,
      jd: null,
      topics: [],
      qa: [],
      experienceLevel: (user && user.experience_level) || '',
      activeDifficulty: 'all',
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

  App.registerRoute('/interview', {
    requiresAuth: true,
    title: 'Interview Prep',
    render: render,
  });
})(window.App);
