# Job Application Assistant

A full-stack web app that streamlines the job-application lifecycle: scrape job
descriptions from LinkedIn/Naukri, extract the required tech stack, match them
against your resume, generate tailored resumes and cover letters, produce
interview-prep material, and track every application from a dashboard.

- **Backend** — Python 3.12 / FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, JWT auth
- **Database** — PostgreSQL 15
- **Frontend** — Vanilla HTML/CSS/JS single-page app (no build step)
- **AI** — LangChain with a configurable LLM provider
- **Documents** — pypdf / python-docx for parsing & generation, WeasyPrint for PDF export

---

## Project layout

```
job_application_assistant/
├── backend/            # FastAPI app, services, routers, Alembic migrations
│   ├── main.py         # app entrypoint
│   ├── config.py       # env-based settings
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── entrypoint.sh   # runs migrations then starts uvicorn (container)
│   └── migrations/     # Alembic
├── frontend/           # static SPA
│   ├── index.html
│   ├── Dockerfile      # nginx image (serves SPA + proxies /api)
│   └── nginx.conf
├── docker-compose.yml  # db + backend + frontend
├── .env.example
└── README.md
```

---

## Prerequisites

| Running locally                    | Running in containers       |
| ---------------------------------- | --------------------------- |
| Python 3.12+                       | Docker 24+                  |
| PostgreSQL 15 (running & reachable)| Docker Compose v2           |
| An LLM endpoint (see below)        | An LLM endpoint (see below) |

### LLM provider — no OpenAI key required

The AI features (edit suggestions, interview Q&A, cover letters, tech-stack
extraction) call a chat model through an **OpenAI-compatible** API. You do
**not** need an OpenAI key — point it at any compatible provider via
`LLM_API_BASE`. Pick one and set it in `.env` (examples are in `.env.example`):

| Provider        | Cost            | `LLM_API_BASE`                        | Example `LLM_MODEL`                      | Key source |
| --------------- | --------------- | ------------------------------------- | ---------------------------------------- | ---------- |
| **Groq**        | Free tier, fast | `https://api.groq.com/openai/v1`      | `llama-3.3-70b-versatile`                | https://console.groq.com/keys |
| **Ollama**      | Free, local     | `http://localhost:11434/v1`           | `llama3.1`                               | none (use any placeholder) |
| **OpenRouter**  | Free-tier models| `https://openrouter.ai/api/v1`        | `meta-llama/llama-3.1-8b-instruct:free`  | https://openrouter.ai/keys |
| **OpenAI**      | Paid            | *(leave unset)*                       | `gpt-4o-mini`                            | https://platform.openai.com |

> **Recommended (no OpenAI key):** Groq. Create a free key, then in `.env`:
> ```
> LLM_MODEL=llama-3.3-70b-versatile
> LLM_API_KEY=<your-groq-key>
> LLM_API_BASE=https://api.groq.com/openai/v1
> ```
> For Ollama (fully local), run `ollama serve` and `ollama pull llama3.1`
> first; set `LLM_API_KEY=ollama` (any non-empty placeholder).

> **WeasyPrint note:** the interview-prep **PDF export** needs native
> GTK/Pango/Cairo libraries. These are installed automatically in the Docker
> image, so **containers are the easiest way to get PDF export working**,
> especially on Windows. Everything else runs fine without them.

---

## 1. Configure environment

From the `job_application_assistant/` directory:

```bash
cp .env.example .env
```

Edit `.env` and set at least:

- An **LLM provider** — e.g. Groq (free). Set `LLM_MODEL`, `LLM_API_KEY`, and
  `LLM_API_BASE` per the provider table above. No OpenAI key needed.
- `JWT_SECRET` — any long random string for production

Key variables:

| Variable                 | Purpose                                            | Default                         |
| ------------------------ | -------------------------------------------------- | ------------------------------- |
| `DATABASE_URL`           | Async DB URL (local host runs)                     | `...@localhost:5432/...`        |
| `POSTGRES_USER/PASSWORD/DB` | Credentials for the `db` container (compose)    | `jaa_user` / `jaa_pass` / `job_application_assistant` |
| `JWT_SECRET`             | Signs auth tokens                                  | change me                       |
| `LLM_MODEL`              | Model name for the chosen provider                 | `llama-3.3-70b-versatile` (Groq)|
| `LLM_API_KEY`            | LLM credentials (any OpenAI-compatible provider)   | *(set yours)*                   |
| `LLM_API_BASE`           | Provider endpoint (omit for OpenAI)                | Groq endpoint                   |
| `BACKEND_PORT`           | API port                                           | `8000`                          |

---

## 2. Run locally (on your host)

### 2a. Start PostgreSQL

Use any Postgres 15 instance. A quick one via Docker:

```bash
docker run --name jaa-db -e POSTGRES_USER=jaa_user -e POSTGRES_PASSWORD=jaa_pass \
  -e POSTGRES_DB=job_application_assistant -p 5432:5432 -d postgres:15-alpine
```

Make sure `DATABASE_URL` in `.env` points at it (the default already does).

### 2b. Install backend dependencies

```bash
cd job_application_assistant
python -m venv .venv

# Windows (bash/Git Bash):
source .venv/Scripts/activate
# macOS / Linux:
# source .venv/bin/activate

pip install -r backend/requirements.txt
```

### 2c. Apply database migrations

```bash
cd backend
alembic upgrade head
```

### 2d. Start the API

```bash
# from job_application_assistant/backend
python main.py
# or: uvicorn main:app --reload
```

The API is now at:

- App: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### 2e. Serve the frontend

The SPA is static and talks to `http://localhost:8000` by default. Serve it
with any static server:

```bash
cd job_application_assistant/frontend
python -m http.server 8080
```

Open http://localhost:8080 in your browser, then register an account and log in.

> If you serve the frontend on a different origin than the API, keep
> `CORS_ORIGINS=["*"]` (the default) in `.env`.

---

## 3. Run in containers (recommended)

This builds three services — `db`, `backend`, `frontend` — wired together.
nginx serves the SPA and reverse-proxies `/api` to the backend, so the browser
uses a single origin (no CORS setup needed). Migrations run automatically on
backend startup.

From `job_application_assistant/`:

```bash
cp .env.example .env     # set LLM_API_KEY and a strong JWT_SECRET
docker compose up --build
```

Then open:

- **App (frontend):** http://localhost:8080
- **API directly:** http://localhost:8000 (docs at `/docs`)

Common commands:

```bash
docker compose up --build -d     # run in the background
docker compose logs -f backend   # follow backend logs
docker compose ps                # service status
docker compose down              # stop and remove containers
docker compose down -v           # also remove volumes (wipes the database)
```

### What each service does

| Service    | Image/Build            | Port (host→container) | Notes                                               |
| ---------- | ---------------------- | --------------------- | --------------------------------------------------- |
| `db`       | `postgres:15-alpine`   | 5432→5432             | Data persisted in the `pgdata` volume               |
| `backend`  | `backend/Dockerfile`   | 8000→8000             | Runs `alembic upgrade head` then uvicorn            |
| `frontend` | `frontend/Dockerfile`  | 8080→80               | nginx; serves SPA and proxies `/api`, `/docs`       |

Uploaded resumes and generated documents persist in the `uploads` and
`generated` volumes.

---

## Troubleshooting

- **Backend can't reach the database** — confirm Postgres is running and
  `DATABASE_URL` is correct. In compose, the backend uses the `db` service host
  automatically; locally it uses `localhost:5432`.
- **LLM features error out** — set a valid `LLM_MODEL`, `LLM_API_KEY`, and
  `LLM_API_BASE` in `.env` (see the provider table above). Scraping, parsing,
  keyword matching, and the dashboard work without the LLM, but
  suggestion/Q&A/cover-letter generation require it.
- **Using Ollama from the containers** — inside Docker, `localhost` points at
  the container, not your host. Set
  `LLM_API_BASE=http://host.docker.internal:11434/v1` so the backend container
  can reach an Ollama instance running on your machine.
- **PDF export fails (`libgobject`/WeasyPrint error)** — you're running on a
  host without GTK libraries. Use the Docker setup (section 3), where these are
  installed in the image.
- **CORS errors in the browser (local run)** — ensure `CORS_ORIGINS=["*"]` in
  `.env`, or serve the frontend behind the containerized nginx proxy.
- **`alembic` command not found** — activate your virtualenv and run it from
  `backend/`.

---

## API overview

All feature endpoints are under `/api` and require a JWT Bearer token obtained
from `/api/auth/login`. Full, interactive documentation is available at `/docs`
when the backend is running.
