# Finance Manager — System Architecture & Design

## Tech Stack Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend Framework | FastAPI (Python 3.10+) | REST API with async support |
| ORM | SQLAlchemy 2.x | Database models & queries |
| Database | PostgreSQL 15 | Persistent data storage |
| Authentication | python-jose (JWT) + passlib (bcrypt) | Token-based auth |
| Validation | Pydantic v2 | Request/response schemas |
| Server | Uvicorn | ASGI server with hot-reload |
| Containerization | Docker Compose | PostgreSQL + pgAdmin |
| Frontend | Vanilla HTML/CSS/JS | Single-page application |
| DB Admin | pgAdmin 4 | Database management GUI |

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                                │
│                                                                     │
│   ┌───────────────────────────────────────────────────────────┐     │
│   │              Frontend (index.html)                          │     │
│   │         Single-Page App • Dark/Light Theme                 │     │
│   │    HTML/CSS/JS • Fetch API • LocalStorage (JWT)            │     │
│   └──────────────────────────┬────────────────────────────────┘     │
└──────────────────────────────┼──────────────────────────────────────┘
                               │ HTTP/REST (JSON)
                               │ Authorization: Bearer <token>
┌──────────────────────────────┼──────────────────────────────────────┐
│                          API LAYER                                   │
│                               ▼                                     │
│   ┌───────────────────────────────────────────────────────────┐     │
│   │              FastAPI Application (main.py)                  │     │
│   │          CORS Middleware • Route Registration               │     │
│   ├───────────────────────────────────────────────────────────┤     │
│   │                      ROUTERS                               │     │
│   │  ┌──────────┐ ┌────────────┐ ┌─────────────┐             │     │
│   │  │  Auth    │ │ Categories │ │  Expenses   │             │     │
│   │  │ /api/auth│ │/api/categ..│ │/api/expenses│             │     │
│   │  └──────────┘ └────────────┘ └─────────────┘             │     │
│   │  ┌──────────┐ ┌────────────┐                              │     │
│   │  │  Loans   │ │ Dashboard  │                              │     │
│   │  │/api/loans│ │/api/dashb..│                              │     │
│   │  └──────────┘ └────────────┘                              │     │
│   ├───────────────────────────────────────────────────────────┤     │
│   │              MIDDLEWARE & SERVICES                          │     │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │     │
│   │  │ auth.py      │  │ schemas.py   │  │ config.py    │    │     │
│   │  │ JWT + bcrypt │  │ Pydantic     │  │ Environment  │    │     │
│   │  └──────────────┘  └──────────────┘  └──────────────┘    │     │
│   └──────────────────────────┬────────────────────────────────┘     │
└──────────────────────────────┼──────────────────────────────────────┘
                               │ SQLAlchemy ORM
┌──────────────────────────────┼──────────────────────────────────────┐
│                         DATA LAYER                                   │
│                               ▼                                     │
│   ┌───────────────────────────────────────────────────────────┐     │
│   │           PostgreSQL 15 (Docker Container)                 │     │
│   │                                                           │     │
│   │   ┌────────┐  ┌────────────┐  ┌──────────┐  ┌───────┐   │     │
│   │   │ users  │  │ categories │  │ expenses │  │ loans │   │     │
│   │   └────────┘  └────────────┘  └──────────┘  └───────┘   │     │
│   │                                                           │     │
│   │   Volume: pgdata (persistent)                             │     │
│   └───────────────────────────────────────────────────────────┘     │
│                                                                     │
│   ┌───────────────────────────────────────────────────────────┐     │
│   │              pgAdmin 4 (Port 5050)                         │     │
│   └───────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Table: `users`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Unique user identifier |
| email | VARCHAR(255) | UNIQUE, NOT NULL, INDEX | Login email |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt-hashed password |
| name | VARCHAR(255) | NOT NULL | Display name |
| role | VARCHAR(50) | DEFAULT 'user' | User role |
| monthly_budget | NUMERIC(12,2) | DEFAULT 0 | Monthly spending limit |
| created_at | TIMESTAMP | DEFAULT now() | Registration timestamp |

### Table: `categories`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Unique category ID |
| user_id | UUID | FK → users.id, ON DELETE CASCADE | Owner |
| name | VARCHAR(100) | NOT NULL | Category name |
| color | VARCHAR(20) | NOT NULL | Hex color code |
| is_default | BOOLEAN | DEFAULT false | Seeded category flag |
| created_at | TIMESTAMP | DEFAULT now() | Creation timestamp |

**Constraints:** `UNIQUE(user_id, name)` — each user has unique category names.

### Table: `expenses`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Unique expense ID |
| user_id | UUID | FK → users.id, ON DELETE CASCADE | Owner |
| category_id | UUID | FK → categories.id, ON DELETE CASCADE | Linked category |
| amount | NUMERIC(12,2) | NOT NULL | Expense amount |
| date | DATE | NOT NULL | Date of expense |
| notes | TEXT | NULLABLE | Optional description |
| created_at | TIMESTAMP | DEFAULT now() | Creation timestamp |

### Table: `loans`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Unique loan ID |
| user_id | UUID | FK → users.id, ON DELETE CASCADE | Owner |
| borrower_name | VARCHAR(255) | NOT NULL | Borrower's name |
| borrower_phone | VARCHAR(50) | NULLABLE | Contact phone |
| borrower_email | VARCHAR(255) | NULLABLE | Contact email |
| principal | NUMERIC(14,2) | NOT NULL | Loan amount |
| roi | NUMERIC(6,4) | NOT NULL | Rate of interest |
| tenure_months | INTEGER | NOT NULL | Loan duration |
| rate_type | ENUM(per_annum, per_month) | NOT NULL, DEFAULT per_annum | Rate period |
| interest_type | ENUM(simple, compound) | NOT NULL, DEFAULT simple | Calculation method |
| monthly_payment | NUMERIC(14,2) | NULLABLE | Calculated EMI |
| total_interest | NUMERIC(14,2) | NULLABLE | Total interest payable |
| created_at | TIMESTAMP | DEFAULT now() | Creation timestamp |

### Entity-Relationship Diagram

```
┌──────────┐       1:N        ┌────────────┐       1:N        ┌──────────┐
│  users   │──────────────────│ categories │──────────────────│ expenses │
│          │                  │            │                  │          │
│ id (PK)  │                  │ id (PK)    │                  │ id (PK)  │
│ email    │                  │ user_id(FK)│                  │ user_id  │
│ name     │                  │ name       │                  │ cat_id   │
│ budget   │                  │ color      │                  │ amount   │
└──────────┘                  └────────────┘                  │ date     │
      │                                                       └──────────┘
      │            1:N        ┌──────────┐
      └───────────────────────│  loans   │
                              │          │
                              │ id (PK)  │
                              │ user_id  │
                              │ principal│
                              └──────────┘
```

---

## API Routes

| Method | Path | Description | Auth Required |
|--------|------|-------------|:---:|
| GET | `/` | Health check / API info | ✗ |
| POST | `/api/auth/register` | Create new user account | ✗ |
| POST | `/api/auth/login` | Authenticate, get JWT | ✗ |
| GET | `/api/auth/me` | Get current user profile | ✓ |
| GET | `/api/dashboard` | Budget summary & stats | ✓ |
| PUT | `/api/budget` | Update monthly budget | ✓ |
| GET | `/api/categories` | List user's categories | ✓ |
| POST | `/api/categories` | Create new category | ✓ |
| PUT | `/api/categories/{id}` | Update category name/color | ✓ |
| DELETE | `/api/categories/{id}` | Delete category | ✓ |
| GET | `/api/expenses` | List expenses (filter: month, year) | ✓ |
| POST | `/api/expenses` | Create new expense | ✓ |
| DELETE | `/api/expenses/{id}` | Delete expense | ✓ |
| GET | `/api/expenses/export` | Export expenses as CSV | ✓ |
| GET | `/api/loans` | List user's loans | ✓ |
| POST | `/api/loans` | Create new loan | ✓ |
| DELETE | `/api/loans/{id}` | Delete loan | ✓ |
| GET | `/api/loans/{id}/schedule` | Get repayment schedule | ✓ |

---

## Component Interaction Diagram

```
┌─────────────┐         ┌─────────────────────────────────────┐
│   Browser   │  HTTP   │          FastAPI (Uvicorn)           │
│             │────────▶│                                     │
│ index.html  │◀────────│  ┌─────────┐    ┌──────────────┐   │
│ styles.css  │  JSON   │  │ Routers │───▶│ models.py    │   │
│ app.js      │         │  └────┬────┘    │ (SQLAlchemy) │   │
│             │         │       │         └──────┬───────┘   │
│ localStorage│         │  ┌────▼────┐           │           │
│ (JWT token) │         │  │auth.py  │    ┌──────▼───────┐   │
│             │         │  │(JWT/pwd)│    │  PostgreSQL  │   │
└─────────────┘         │  └─────────┘    │  (Docker)    │   │
                        │                 └──────────────┘   │
                        └─────────────────────────────────────┘
```

---

## Authentication Flow

```
┌────────┐                    ┌────────┐                    ┌──────┐
│ Client │                    │  API   │                    │  DB  │
└───┬────┘                    └───┬────┘                    └──┬───┘
    │                             │                            │
    │  POST /api/auth/register    │                            │
    │  {email, password, name}    │                            │
    ├────────────────────────────▶│                            │
    │                             │  Check email uniqueness    │
    │                             ├───────────────────────────▶│
    │                             │◀───────────────────────────┤
    │                             │                            │
    │                             │  bcrypt(password) → hash   │
    │                             │  INSERT user               │
    │                             ├───────────────────────────▶│
    │                             │  INSERT 5 default cats     │
    │                             ├───────────────────────────▶│
    │                             │◀───────────────────────────┤
    │                             │                            │
    │                             │  jwt.encode({sub, email})  │
    │  {access_token, user}       │                            │
    │◀────────────────────────────┤                            │
    │                             │                            │
    │  GET /api/expenses          │                            │
    │  Authorization: Bearer tkn  │                            │
    ├────────────────────────────▶│                            │
    │                             │  jwt.decode(token)         │
    │                             │  Query user by sub (id)    │
    │                             ├───────────────────────────▶│
    │                             │◀───────────────────────────┤
    │                             │                            │
    │                             │  Query expenses            │
    │                             │  WHERE user_id = current   │
    │                             ├───────────────────────────▶│
    │  [{expense}, ...]           │◀───────────────────────────┤
    │◀────────────────────────────┤                            │
    │                             │                            │
```

### Token Lifecycle
1. User registers or logs in → server returns `access_token` (JWT, HS256)
2. Client stores token in `localStorage`
3. All subsequent requests include `Authorization: Bearer <token>` header
4. Server decodes token via `python-jose`, extracts `sub` (user ID)
5. Token expires after 1440 minutes (24 hours)
6. On 401 response, client redirects to login page

---

## Error Handling Strategy

| HTTP Code | Scenario | Response Body |
|-----------|----------|---------------|
| 400 | Bad request / malformed input | `{"detail": "..."}` |
| 401 | Missing/invalid/expired token | `{"detail": "Invalid or expired token"}` |
| 404 | Resource not found | `{"detail": "... not found"}` |
| 409 | Conflict (duplicate email/category) | `{"detail": "Email already registered"}` |
| 422 | Validation error (Pydantic) | `{"detail": [{field, msg, type}]}` |
| 500 | Unhandled server error | `{"detail": "Internal server error"}` |

**Principles:**
- All errors return JSON with a `detail` field
- Pydantic handles input validation automatically (422)
- HTTPException raised explicitly for business logic errors
- User-scoped queries return 404 (not 403) to prevent enumeration

---

## Data Flow: Key Operations

### Register User
```
Input: {email, password, name}
  → Validate via UserRegister schema (Pydantic)
  → Check email uniqueness in DB
  → Hash password with bcrypt
  → INSERT into users table
  → INSERT 5 default categories
  → Generate JWT with user.id as subject
  → Return {access_token, user}
```

### Add Expense
```
Input: {amount, category_id, date, notes} + Bearer token
  → Decode JWT → get current user
  → Validate via ExpenseCreate schema
  → Verify category_id belongs to current user
  → INSERT into expenses table
  → Return ExpenseResponse with category name/color
```

### Get Dashboard
```
Input: Bearer token (+ optional month/year query params)
  → Decode JWT → get current user
  → Query: SUM(expenses.amount) WHERE month = current month
  → Query: COUNT categories, COUNT expenses
  → Query: GROUP BY category for breakdown
  → Query: recent 5 expenses with category join
  → Return DashboardResponse
```

### Generate Loan Schedule
```
Input: loan_id path param + Bearer token
  → Decode JWT → get current user
  → Fetch loan WHERE id = loan_id AND user_id = current
  → Calculate based on interest_type:
    - Simple: flat interest per month
    - Compound: EMI formula with diminishing balance
  → Return [{month, opening_balance, interest, principal, payment, closing_balance}]
```
