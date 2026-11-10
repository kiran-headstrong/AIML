/* =========================================================================
   JD comparison page (js/pages/compare.js)

   Route: #/compare

   Lets the user pick two or more analysed job descriptions and compare them
   side by side:
     * a multi-select picker populated from the user's tracked job entries
       (dashboard) — Requirement 13.1
     * a side-by-side table showing job title, company, required skills,
       preferred skills, experience required, and match score per JD
       — Requirement 13.2
     * common required skills (shared across all selected JDs) and the
       skills unique to each JD, highlighted — Requirement 13.3
     * the role with the highest match score flagged — Requirement 13.4

   The list of selectable JDs comes from GET /api/dashboard (each tracked job
   entry references a scraped JD). The comparison is computed by POST
   /api/compare with the selected JD ids.

   Registers the /compare route, overriding the placeholder stub (loaded
   after placeholders.js in index.html).
   ========================================================================= */
(function (App) {
  'use strict';

  const UI = App.UI;
  const Api = App.Api;
  const Router = App.Router;
  const ApiError = App.ApiError;

  // Page-local state.
  let state = {
    entries: [], // dashboard entries available to compare
    selected: {}, // jd_id -> true
    result: null, // last CompareResponse
  };

  function header() {
    return (
      '<div class="page-header">' +
        '<h1 class="page-title">Compare JDs</h1>' +
        '<p class="page-subtitle">Select two or more analyzed jobs to ' +
        'compare them side by side.</p>' +
      '</div>'
    );
  }

  function emptyEntriesView(view) {
    view.innerHTML =
      header() +
      '<div class="card"><div class="empty-state">' +
        '<div class="empty-icon">⚖️</div>' +
        '<h2>Nothing to compare yet</h2>' +
        '<p class="muted">Scrape and analyze at least two job descriptions, ' +
        'then come back to compare them.</p>' +
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

  function round(n) {
    return Math.round((Number(n) || 0) * 10) / 10;
  }

  // ---- Picker card ------------------------------------------------------

  function pickerCard() {
    const rows = state.entries
      .map(function (e) {
        const checked = state.selected[e.jd_id] ? ' checked' : '';
        const score =
          e.match_score !== null && e.match_score !== undefined
            ? round(e.match_score) + '%'
            : '—';
        return (
          '<label class="pick-row">' +
            '<input type="checkbox" class="pick-check" ' +
              'data-jd="' + UI.escape(e.jd_id) + '"' + checked + ' />' +
            '<span class="pick-main">' +
              '<span class="pick-title">' + UI.escape(e.job_title) + '</span>' +
              '<span class="pick-company">' + UI.escape(e.company_name) + '</span>' +
            '</span>' +
            '<span class="pick-score">' + score + '</span>' +
          '</label>'
        );
      })
      .join('');

    const selectedCount = Object.keys(state.selected).filter(function (k) {
      return state.selected[k];
    }).length;

    return (
      '<div class="card">' +
        '<div class="card-header">' +
          '<h2>Select jobs</h2>' +
          '<span class="muted">' + selectedCount + ' selected</span>' +
        '</div>' +
        '<div id="compare-error" class="form-error" hidden></div>' +
        '<div class="pick-list">' + rows + '</div>' +
        '<div class="btn-row">' +
          '<button class="btn" id="run-compare" type="button"' +
            (selectedCount >= 2 ? '' : ' disabled') + '>Compare selected</button>' +
          '<button class="btn btn-secondary" id="clear-compare" type="button"' +
            (selectedCount ? '' : ' disabled') + '>Clear</button>' +
        '</div>' +
      '</div>'
    );
  }

  // ---- Comparison table -------------------------------------------------

  function skillCells(items, resultForHighlight) {
    // Required skills row — highlight common (across all) and unique skills.
    const common = {};
    ((resultForHighlight && resultForHighlight.common_skills) || []).forEach(
      function (s) {
        common[s.toLowerCase()] = true;
      }
    );
    const uniqueMap = (resultForHighlight && resultForHighlight.unique_skills) || {};

    return items
      .map(function (item) {
        const unique = {};
        (uniqueMap[String(item.jd_id)] || []).forEach(function (s) {
          unique[s.toLowerCase()] = true;
        });

        const chips = (item.required_skills || []).length
          ? '<div class="chip-row">' +
            item.required_skills
              .map(function (s) {
                const key = s.toLowerCase();
                let cls = 'chip';
                if (common[key]) cls = 'chip chip-matched';
                else if (unique[key]) cls = 'chip chip-tech';
                return '<span class="' + cls + '">' + UI.escape(s) + '</span>';
              })
              .join('') +
            '</div>'
          : '<span class="muted">None listed.</span>';
        return '<td>' + chips + '</td>';
      })
      .join('');
  }

  function preferredSkillCells(items) {
    return items
      .map(function (item) {
        const chips = (item.preferred_skills || []).length
          ? '<div class="chip-row">' +
            item.preferred_skills
              .map(function (s) {
                return '<span class="chip">' + UI.escape(s) + '</span>';
              })
              .join('') +
            '</div>'
          : '<span class="muted">None listed.</span>';
        return '<td>' + chips + '</td>';
      })
      .join('');
  }

  function resultCard(result) {
    const items = (result && result.items) || [];
    if (!items.length) return '';

    const highest = result.highest_match_jd_id;

    // Header row: one column per JD, flagging the highest match.
    const headCells = items
      .map(function (item) {
        const isBest =
          highest && String(item.jd_id) === String(highest);
        const flag = isBest
          ? ' <span class="badge badge-success">Best match</span>'
          : '';
        return (
          '<th>' + UI.escape(item.job_title) + flag + '</th>'
        );
      })
      .join('');

    const companyCells = items
      .map(function (item) {
        return '<td>' + UI.escape(item.company_name) + '</td>';
      })
      .join('');

    const experienceCells = items
      .map(function (item) {
        return '<td>' + UI.escape(item.experience_required || '—') + '</td>';
      })
      .join('');

    const scoreCells = items
      .map(function (item) {
        const isBest = highest && String(item.jd_id) === String(highest);
        const score =
          item.match_score !== null && item.match_score !== undefined
            ? round(item.match_score) + '%'
            : '—';
        const cls = isBest ? ' class="compare-best"' : '';
        return '<td' + cls + '>' + score + '</td>';
      })
      .join('');

    const common = (result.common_skills || []).length
      ? '<div class="chip-row">' +
        result.common_skills
          .map(function (s) {
            return '<span class="chip chip-matched">' + UI.escape(s) + '</span>';
          })
          .join('') +
        '</div>'
      : '<p class="muted">No required skills are shared across all selected ' +
        'jobs.</p>';

    return (
      '<div class="card">' +
        '<div class="card-header"><h2>Comparison</h2></div>' +
        '<div class="table-wrap">' +
          '<table class="table compare-table">' +
            '<thead><tr><th>Attribute</th>' + headCells + '</tr></thead>' +
            '<tbody>' +
              '<tr><th>Company</th>' + companyCells + '</tr>' +
              '<tr><th>Experience required</th>' + experienceCells + '</tr>' +
              '<tr><th>Match score</th>' + scoreCells + '</tr>' +
              '<tr><th>Required skills</th>' +
                skillCells(items, result) + '</tr>' +
              '<tr><th>Preferred skills</th>' +
                preferredSkillCells(items) + '</tr>' +
            '</tbody>' +
          '</table>' +
        '</div>' +
        '<h3 class="subhead">Common required skills</h3>' +
        common +
        '<p class="form-hint">Green chips are required by every selected job; ' +
        'blue chips are unique to one job.</p>' +
      '</div>'
    );
  }

  // ---- Error helpers ----------------------------------------------------

  function showError(message) {
    const el = document.getElementById('compare-error');
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
  }

  function clearError() {
    const el = document.getElementById('compare-error');
    if (el) el.hidden = true;
  }

  // ---- Rendering + binding ---------------------------------------------

  function renderBody(view) {
    view.innerHTML =
      header() +
      pickerCard() +
      (state.result ? resultCard(state.result) : '');
    bindPicker(view);
  }

  function bindPicker(view) {
    view.querySelectorAll('.pick-check').forEach(function (cb) {
      cb.addEventListener('change', function () {
        const jdId = cb.getAttribute('data-jd');
        if (cb.checked) state.selected[jdId] = true;
        else delete state.selected[jdId];
        // Re-render to refresh the selected count + button enabled state.
        renderBody(view);
      });
    });

    const runBtn = view.querySelector('#run-compare');
    if (runBtn) {
      runBtn.addEventListener('click', function () {
        runCompare(view);
      });
    }

    const clearBtn = view.querySelector('#clear-compare');
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        state.selected = {};
        state.result = null;
        renderBody(view);
      });
    }
  }

  async function runCompare(view) {
    clearError();
    const ids = Object.keys(state.selected).filter(function (k) {
      return state.selected[k];
    });
    if (ids.length < 2) {
      showError('Select at least two jobs to compare.');
      return;
    }

    const runBtn = view.querySelector('#run-compare');
    const original = runBtn ? runBtn.innerHTML : '';
    if (runBtn) {
      runBtn.disabled = true;
      runBtn.innerHTML = '<span class="spinner"></span> Comparing...';
    }

    try {
      const res = await Api.post('/api/compare', { body: { jd_ids: ids } });
      state.result = res;
      renderBody(view);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : 'Failed to compare the selected jobs. Please try again.';
      showError(message);
      if (runBtn) {
        runBtn.disabled = false;
        runBtn.innerHTML = original;
      }
    }
  }

  async function render(view) {
    state = { entries: [], selected: {}, result: null };
    view.innerHTML = header() + UI.renderLoading('Loading your jobs...');

    let dashboard;
    try {
      dashboard = await Api.get('/api/dashboard');
    } catch (err) {
      throw err; // handled by the router's error boundary
    }

    const entries = (dashboard && dashboard.entries) || [];
    if (entries.length < 2) {
      emptyEntriesView(view);
      return;
    }

    state.entries = entries;
    renderBody(view);
  }

  App.registerRoute('/compare', {
    requiresAuth: true,
    title: 'Compare JDs',
    render: render,
  });
})(window.App);
