/* =========================================================================
   Match & Suggestions page (js/pages/match.js)

   Route: #/match   (optional ?jd=<jd_id> to target a specific JD)

   Shows how the user's base resume matches a scraped JD and the ways to
   improve it:
     * overall match score + skills/experience/education sub-scores, with the
       category label (Strong/Moderate/Weak) — Requirements 4.1-4.4
     * matched & missing skills and experience keywords — Requirement 4.2
     * resume edit suggestions grouped by category and ordered by impact
       (high first) — Requirements 5.1-5.3
     * skill-gap analysis with Critical/Recommended priority labels and
       learning resources — Requirements 11.1-11.4
     * buttons to generate a tailored resume and download it — Requirement 6.4

   The target JD is taken from the ?jd query param (e.g. navigated from the JD
   page) or the remembered "selected JD" (App.Store). When none exists the
   page prompts the user to scrape a JD first.

   Registers the /match route, overriding the placeholder stub (loaded after
   placeholders.js in index.html).
   ========================================================================= */
(function (App) {
  'use strict';

  const UI = App.UI;
  const Api = App.Api;
  const Store = App.Store;
  const Router = App.Router;
  const ApiError = App.ApiError;

  // Ordering + labels for suggestion categories and impact tiers.
  const SUGGESTION_CATEGORIES = [
    ['skills_to_add', 'Skills to add'],
    ['experience_rephrase', 'Experience to rephrase'],
    ['keywords_to_include', 'Keywords to include'],
    ['sections_reorder', 'Sections to reorder or emphasize'],
  ];
  const IMPACT_ORDER = { high: 0, medium: 1, low: 2 };
  const IMPACT_BADGE = {
    high: 'badge-danger',
    medium: 'badge-warning',
    low: 'badge-neutral',
  };
  const CATEGORY_BADGE = {
    'Strong Match': 'badge-success',
    'Moderate Match': 'badge-warning',
    'Weak Match': 'badge-danger',
  };
  const GAP_BADGE = { Critical: 'badge-danger', Recommended: 'badge-warning' };

  function header(jd) {
    const subtitle = jd
      ? UI.escape(jd.job_title) +
        (jd.company_name ? ' · ' + UI.escape(jd.company_name) : '')
      : 'See how your resume matches a job and get tailored suggestions.';
    return (
      '<div class="page-header">' +
        '<h1 class="page-title">Match &amp; Suggestions</h1>' +
        '<p class="page-subtitle">' + subtitle + '</p>' +
      '</div>'
    );
  }

  function noJdView(view) {
    view.innerHTML =
      header(null) +
      '<div class="card"><div class="empty-state">' +
        '<div class="empty-icon">🎯</div>' +
        '<h2>No job selected</h2>' +
        '<p class="muted">Scrape a job description first, then come back to ' +
        'see your match.</p>' +
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

  function scoreCard(match) {
    const badge = CATEGORY_BADGE[match.category] || 'badge-neutral';
    return (
      '<div class="card">' +
        '<div class="card-header">' +
          '<h2>Match score</h2>' +
          '<span class="badge ' + badge + '">' + UI.escape(match.category) + '</span>' +
        '</div>' +
        '<div class="score-hero">' +
          '<div class="score-ring">' + round(match.overall_score) +
            '<span class="score-unit">%</span></div>' +
          '<div class="score-subs">' +
            subScore('Skills', match.skills_score) +
            subScore('Experience', match.experience_score) +
            subScore('Education', match.education_score) +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  function subScore(label, value) {
    const pct = Math.max(0, Math.min(100, Number(value) || 0));
    return (
      '<div class="subscore">' +
        '<div class="subscore-head">' +
          '<span>' + UI.escape(label) + '</span>' +
          '<span class="subscore-val">' + round(value) + '%</span>' +
        '</div>' +
        '<div class="meter"><div class="meter-fill" style="width:' + pct + '%"></div></div>' +
      '</div>'
    );
  }

  function pills(items, variant) {
    if (!items || !items.length) {
      return '<p class="muted">None.</p>';
    }
    const cls = variant === 'missing' ? 'chip chip-missing' : 'chip chip-matched';
    return (
      '<div class="chip-row">' +
      items
        .map(function (s) {
          return '<span class="' + cls + '">' + UI.escape(s) + '</span>';
        })
        .join('') +
      '</div>'
    );
  }

  function breakdownCard(match) {
    return (
      '<div class="card">' +
        '<div class="card-header"><h2>Skill &amp; keyword breakdown</h2></div>' +
        '<div class="split-cols">' +
          '<div>' +
            '<h3 class="subhead">Matched skills</h3>' +
            pills(match.matched_skills, 'matched') +
            '<h3 class="subhead">Matched experience keywords</h3>' +
            pills(match.matched_experience_keywords, 'matched') +
          '</div>' +
          '<div>' +
            '<h3 class="subhead">Missing skills</h3>' +
            pills(match.missing_skills, 'missing') +
            '<h3 class="subhead">Missing experience keywords</h3>' +
            pills(match.missing_experience_keywords, 'missing') +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  function suggestionsCard(suggestions) {
    const list = suggestions || [];
    if (!list.length) {
      return (
        '<div class="card">' +
          '<div class="card-header"><h2>Edit suggestions</h2></div>' +
          '<p class="muted">No suggestions available.</p>' +
        '</div>'
      );
    }

    // Group by category (in the defined order), sort each group by impact.
    let body = '';
    SUGGESTION_CATEGORIES.forEach(function (pair) {
      const key = pair[0];
      const label = pair[1];
      const group = list
        .filter(function (s) {
          return s.category === key;
        })
        .sort(function (a, b) {
          return (IMPACT_ORDER[a.impact] ?? 3) - (IMPACT_ORDER[b.impact] ?? 3);
        });
      if (!group.length) return;

      body +=
        '<h3 class="subhead">' + UI.escape(label) + '</h3>' +
        '<ul class="suggestion-list">' +
        group
          .map(function (s) {
            const impactBadge = IMPACT_BADGE[s.impact] || 'badge-neutral';
            let extra = '';
            if (s.original_text || s.suggested_text) {
              extra = '<div class="suggestion-diff">';
              if (s.original_text) {
                extra +=
                  '<div class="diff-before"><span class="diff-tag">Before</span>' +
                  UI.escape(s.original_text) + '</div>';
              }
              if (s.suggested_text) {
                extra +=
                  '<div class="diff-after"><span class="diff-tag">After</span>' +
                  UI.escape(s.suggested_text) + '</div>';
              }
              extra += '</div>';
            }
            return (
              '<li class="suggestion-item">' +
                '<div class="suggestion-head">' +
                  '<span class="badge ' + impactBadge + '">' +
                    UI.escape((s.impact || '').toUpperCase()) + '</span>' +
                  '<span class="suggestion-desc">' + UI.escape(s.description) + '</span>' +
                '</div>' +
                extra +
              '</li>'
            );
          })
          .join('') +
        '</ul>';
    });

    return (
      '<div class="card">' +
        '<div class="card-header"><h2>Edit suggestions</h2></div>' +
        body +
      '</div>'
    );
  }

  function skillGapCard(gaps) {
    const critical = (gaps && gaps.critical) || [];
    const recommended = (gaps && gaps.recommended) || [];
    const all = critical.concat(recommended);

    if (!all.length) {
      return (
        '<div class="card">' +
          '<div class="card-header"><h2>Skill gap analysis</h2></div>' +
          '<p class="muted">No skill gaps found — your resume covers the ' +
          'listed tech stack.</p>' +
        '</div>'
      );
    }

    function renderGap(gap) {
      const badge = GAP_BADGE[gap.priority] || 'badge-neutral';
      const resources =
        gap.learning_resources && gap.learning_resources.length
          ? '<ul class="resource-list">' +
            gap.learning_resources
              .map(function (r) {
                // Resources may be URLs or plain text suggestions.
                const text = UI.escape(r);
                const isUrl = /^https?:\/\//i.test(r);
                return (
                  '<li>' +
                  (isUrl
                    ? '<a href="' + text + '" target="_blank" rel="noopener">' + text + '</a>'
                    : text) +
                  '</li>'
                );
              })
              .join('') +
            '</ul>'
          : '<p class="muted">No resources suggested.</p>';
      return (
        '<li class="gap-item">' +
          '<div class="gap-head">' +
            '<span class="badge ' + badge + '">' + UI.escape(gap.priority) + '</span>' +
            '<span class="gap-skill">' + UI.escape(gap.skill) + '</span>' +
          '</div>' +
          resources +
        '</li>'
      );
    }

    return (
      '<div class="card">' +
        '<div class="card-header"><h2>Skill gap analysis</h2></div>' +
        '<ul class="gap-list">' +
          all.map(renderGap).join('') +
        '</ul>' +
      '</div>'
    );
  }

  function actionsCard() {
    return (
      '<div class="card">' +
        '<div class="card-header"><h2>Tailored resume</h2></div>' +
        '<p class="muted">Generate a resume tailored to this job with the ' +
        'suggested edits applied, then download it as a Word document.</p>' +
        '<div id="resume-action-error" class="form-error" hidden></div>' +
        '<div class="btn-row">' +
          '<button class="btn" id="gen-resume" type="button">Generate tailored resume</button>' +
          '<button class="btn btn-secondary" id="dl-resume" type="button">Download .docx</button>' +
        '</div>' +
      '</div>'
    );
  }

  function showActionError(message) {
    const el = document.getElementById('resume-action-error');
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
  }

  function clearActionError() {
    const el = document.getElementById('resume-action-error');
    if (el) el.hidden = true;
  }

  async function downloadTailoredResume(jdId) {
    const res = await Api.get(
      '/api/match/' + encodeURIComponent(jdId) + '/download-resume',
      { raw: true }
    );
    const blob = await res.blob();

    // Derive a filename from the Content-Disposition header when present.
    let filename = 'tailored_resume.docx';
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
  }

  function bindActions(jdId) {
    const genBtn = document.getElementById('gen-resume');
    const dlBtn = document.getElementById('dl-resume');

    if (genBtn) {
      genBtn.addEventListener('click', async function () {
        clearActionError();
        genBtn.disabled = true;
        const original = genBtn.innerHTML;
        genBtn.innerHTML = '<span class="spinner"></span> Generating...';
        try {
          await Api.post(
            '/api/match/' + encodeURIComponent(jdId) + '/generate-resume'
          );
          UI.toast('Tailored resume generated. You can download it now.', 'success');
        } catch (err) {
          showActionError(
            err instanceof ApiError
              ? err.message
              : 'Failed to generate the tailored resume.'
          );
        } finally {
          genBtn.disabled = false;
          genBtn.innerHTML = original;
        }
      });
    }

    if (dlBtn) {
      dlBtn.addEventListener('click', async function () {
        clearActionError();
        dlBtn.disabled = true;
        const original = dlBtn.innerHTML;
        dlBtn.innerHTML = '<span class="spinner"></span> Preparing...';
        try {
          await downloadTailoredResume(jdId);
        } catch (err) {
          const message =
            err instanceof ApiError
              ? err.message
              : 'Failed to download the tailored resume.';
          showActionError(message);
          if (err instanceof ApiError && err.status === 404) {
            showActionError('Generate the tailored resume first, then download it.');
          }
        } finally {
          dlBtn.disabled = false;
          dlBtn.innerHTML = original;
        }
      });
    }
  }

  /**
   * Compute the match (POST is idempotent unless recompute=true) and then load
   * suggestions and skill gaps in parallel. Returns a bundle or throws.
   */
  async function loadMatchData(jdId) {
    const match = await Api.post('/api/match/' + encodeURIComponent(jdId));
    const [suggestionsRes, gaps] = await Promise.all([
      Api.get('/api/match/' + encodeURIComponent(jdId) + '/suggestions'),
      Api.get('/api/match/' + encodeURIComponent(jdId) + '/skill-gaps'),
    ]);
    return {
      match: match,
      suggestions: (suggestionsRes && suggestionsRes.suggestions) || [],
      gaps: gaps,
    };
  }

  async function render(view, query) {
    const jdId = (query && query.jd) || (Store.getSelectedJd() || {}).id;
    if (!jdId) {
      noJdView(view);
      return;
    }

    // Resolve a display header; fall back to the cached selected JD, otherwise
    // fetch the JD details for title/company.
    let jd = Store.getSelectedJd();
    if (!jd || jd.id !== jdId) {
      try {
        jd = await Api.get('/api/jd/' + encodeURIComponent(jdId));
        Store.setSelectedJd(jd);
      } catch (e) {
        jd = { id: jdId, job_title: 'Selected job', company_name: '' };
      }
    }

    view.innerHTML = header(jd) + UI.renderLoading('Computing your match...');

    let data;
    try {
      data = await loadMatchData(jdId);
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        // Most commonly: no resume uploaded yet.
        view.innerHTML =
          header(jd) +
          '<div class="card"><div class="empty-state">' +
            '<div class="empty-icon">📄</div>' +
            '<h2>Can\'t compute the match yet</h2>' +
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
      throw err;
    }

    view.innerHTML =
      header(jd) +
      scoreCard(data.match) +
      breakdownCard(data.match) +
      suggestionsCard(data.suggestions) +
      skillGapCard(data.gaps) +
      actionsCard();

    bindActions(jdId);
  }

  App.registerRoute('/match', {
    requiresAuth: true,
    title: 'Match & Suggestions',
    render: render,
  });
})(window.App);
