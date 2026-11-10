# Finance Manager

A full-stack personal finance management application with expense tracking, budget management, category organization, and loan tracking.

## Tech Stack

- **Backend**: Python (FastAPI) with SQLAlchemy ORM
- **Database**: PostgreSQL 15 (Docker)
- **Authentication**: JWT with bcrypt password hashing
- **Frontend**: Single-page HTML/CSS/JS application
- **Containerization**: Docker Compose

---

## Quick Start (Step by Step)

### Prerequisites
- Python 3.12 installed
- Docker Desktop installed and running

### Step 1: Start PostgreSQL

```bash
cd Projects/finance_manager
docker-compose up -d
```

This starts:
- **PostgreSQL** on port `5432`
- **pgAdmin** on port `5050`

### Step 2: Configure Environment

```bash
copy .env.example .env
```
> Defaults work out of the box. No edits needed for local dev.

### Step 3: Create Virtual Environment (recommended)

```bash
py -3.12 -m venv .venv312
.venv312\Scripts\activate
```

### Step 4: Install Python Dependencies

```bash
pip install -r backend/requirements.txt
```

### Step 5: Start Backend

```bash
cd backend
python main.py
```

You'll see:
```
🚀 Starting Finance Manager API on http://0.0.0.0:8000
📖 API Docs: http://localhost:8000/docs
✓ Database tables created/verified
✓ Default admin user created (admin@financemanager.com / admin123)
```

### Step 6: Open Frontend

Open `frontend/index.html` in your browser (double-click it).

---

## Default Admin Account

On first startup, an admin user is automatically created:

| Field | Value |
|-------|-------|
| Email | `admin@financemanager.com` |
| Password | `admin123` |
| Role | `admin` |

### Admin Privileges

The admin has access to all standard features PLUS these exclusive endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/users` | View all registered users |
| GET | `/api/admin/stats` | System-wide statistics (total users, expenses, etc.) |
| DELETE | `/api/admin/users/{id}` | Delete a user and all their data |

Regular users get `403 Forbidden` if they try to access admin routes.

---

## Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| Finance Manager API | http://localhost:8000 | — |
| API Documentation (Swagger) | http://localhost:8000/docs | — |
| pgAdmin (DB viewer) | http://localhost:5050 | admin@finance.local / admin123 |
| Frontend | Open `frontend/index.html` | Register or use admin account |

---

### 5. Open Frontend

Open `frontend/index.html` in your browser (or serve it with any static file server).

## Features

- **User Authentication** - Register/Login with JWT tokens
- **Dashboard** - Monthly budget overview, spending breakdown by category
- **Expenses** - Add, view, filter, delete expenses with CSV export
- **Categories** - Custom color-coded categories (5 defaults seeded on registration)
- **Loans** - Track loans with interest calculations and repayment schedules
- **Themes** - Dark/Light mode toggle
- **User-scoped data** - Each user only sees their own data

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/auth/register | Create account |
| POST | /api/auth/login | Login, get JWT |
| GET | /api/auth/me | Current user info |
| GET | /api/dashboard | Budget summary & stats |
| PUT | /api/budget | Update monthly budget |
| GET | /api/categories | List categories |
| POST | /api/categories | Create category |
| PUT | /api/categories/{id} | Update category |
| DELETE | /api/categories/{id} | Delete category |
| GET | /api/expenses | List expenses (filter by month/year) |
| POST | /api/expenses | Create expense |
| DELETE | /api/expenses/{id} | Delete expense |
| GET | /api/expenses/export | Export CSV |
| GET | /api/loans | List loans |
| POST | /api/loans | Create loan |
| DELETE | /api/loans/{id} | Delete loan |
| GET | /api/loans/{id}/schedule | Repayment schedule |

## Database Schema

- **users** - Accounts with email, password hash, budget
- **categories** - User-scoped expense categories with colors
- **expenses** - Transaction records linked to categories
- **loans** - Loan tracking with interest calculations

## Default Categories (seeded on registration)

1. Food & Dining (#FF6384)
2. Transportation (#36A2EB)
3. Housing & Rent (#FFCE56)
4. Entertainment (#4BC0C0)
5. Utilities (#9966FF)

## Security

- Passwords hashed with bcrypt
- JWT tokens expire after 24 hours
- All data endpoints require authentication
- User-scoped queries prevent data leakage
- CORS enabled for local development
