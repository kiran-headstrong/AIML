# VOUCH by Vectis — Local Prototype

A runnable prototype of the **VOUCH by Vectis** platform described in the project
synopsis. It demonstrates one assessment end-to-end for a single category
(Restaurants), covering intake → evidence → scoring → peer review → senior
approval → business consent → public publication.

Built with **Django + SQLite + local file storage** so it runs on a laptop with
no external database. (The synopsis proposes PostgreSQL for production; SQLite is
used here only to keep local setup zero-config. The data model and access-control
design are the same.)

## What it shows (prototype scope from the synopsis)

- Staff create an assessment and assign a team member.
- The assessor uploads evidence (with SHA-256 integrity hash) and records scores.
- The reviewer / senior approver moves it through the approval stages.
  An assessor cannot approve their own work.
- The business logs into a portal, submits information, sees status, gives consent.
- On approval + consent, a **frozen read-only PublishedReport snapshot** is created.
- The public site reads **only** from that snapshot — never from internal records.
- An append-only **audit trail** logs views, edits and approvals.

## Roles

| Role | Access |
|------|--------|
| Admin | Full internal access + Django admin |
| Assessor | Assigned assessments: evidence + scoring |
| Reviewer / Senior approver | Assigned assessments: review + approval |
| Business | Own assessment only, business-visible data |
| Public | Approved final reports only |

## Run it locally

Requires Python 3.10+.

```bash
# from the vouch/ folder
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt

python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open http://127.0.0.1:8000/

### Demo logins

| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | Admin |
| assessor | assessor123 | Assessor |
| reviewer | reviewer123 | Reviewer / Senior approver |
| business | business123 | Business |

## Suggested walkthrough

1. Log in as **admin** → Dashboard shows the sample assessment "The Olive Garden Bistro".
   Click **Advance stage** until it reaches *Information requested*.
2. Log in as **business** → open the assessment, submit information.
3. Log in as **assessor** → open it, upload an evidence file, enter scores, save a summary.
   Advance through *Evidence gathering* and *Analysis and scoring*.
4. Log in as **reviewer** → advance *Peer review* then *Senior approval*
   (the assessor is blocked from approving their own work).
5. Log in as **business** → the assessment is now *Ready for your review and consent*.
   Click **I consent to publish**.
6. Log in as **reviewer** or **admin** → click **Publish approved report**.
7. Visit the public home page → the approved report is live. Open it to see the
   rating, summary and findings. Internal evidence stays private.

## Confidentiality design

- Internal working data (Assessment, Score, Evidence, summary) is private and
  access-controlled by role **and** per-assessment assignment.
- Evidence files live in `private_media/` and are served only through a
  permission-checked download view (stand-in for signed URLs).
- The public layer reads exclusively from `PublishedReport`, which has no
  foreign key back to internal records.
- Published reports are versioned with a validity date, not overwritten.
```
