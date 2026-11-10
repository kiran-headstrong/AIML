# Changelog

All notable changes to the Finance Manager project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2024-01-15

### Added

#### Authentication
- User registration with email/password (bcrypt hashing)
- JWT-based login with HS256 signing and 24-hour expiration
- `GET /api/auth/me` endpoint for current user profile
- HTTPBearer security scheme for protected routes

#### Expense Tracking
- `POST /api/expenses` — create expense with amount, date, category, and notes
- `GET /api/expenses` — list expenses with month/year query filtering
- `DELETE /api/expenses/{id}` — delete expense with ownership verification
- `GET /api/expenses/export` — CSV export of user's expenses

#### Category Management
- `POST /api/categories` — create custom category with name and hex color
- `GET /api/categories` — list all user categories
- `PUT /api/categories/{id}` — update category name or color
- `DELETE /api/categories/{id}` — delete category (cascades to expenses)
- 5 default categories seeded on registration (Food & Dining, Transportation, Housing & Rent, Entertainment, Utilities)
- Unique constraint on (user_id, name) to prevent duplicates

#### Budget Management
- `PUT /api/budget` — set/update monthly spending budget
- Budget tracking integrated into dashboard view

#### Dashboard
- `GET /api/dashboard` — aggregated monthly summary
- Total spent this month with remaining balance calculation
- Category-wise spending breakdown
- Recent expenses list (last 5)
- Total category and expense counts

#### Loan Management
- `POST /api/loans` — create loan with borrower info, principal, rate, tenure
- `GET /api/loans` — list all user loans
- `DELETE /api/loans/{id}` — delete loan record
- `GET /api/loans/{id}/schedule` — full amortization/repayment table
- Support for simple and compound interest calculations
- Support for per-annum and per-month rate types
- Automatic monthly payment and total interest calculation on creation

#### Frontend
- Single-page application with vanilla HTML/CSS/JS
- Login and registration forms
- Dashboard with budget progress and category breakdown
- Expense management table with filtering
- Category management with color picker
- Loan management with repayment schedule display
- Dark/light theme toggle with localStorage persistence
- Responsive navigation between views

#### Infrastructure
- Docker Compose setup with PostgreSQL 15 and pgAdmin 4
- Persistent volume for database data
- Health check on PostgreSQL container
- Environment-based configuration via `.env` file
- Auto table creation on FastAPI startup
- CORS middleware for local development
- OpenAPI documentation at `/docs`

#### Security
- Passwords hashed with bcrypt via passlib
- JWT tokens with configurable expiration
- User-scoped data queries (no cross-user access)
- Input validation via Pydantic schemas
- Proper HTTP error codes (401, 404, 409, 422)

---

## [Unreleased]

### Planned
- Recurring expense automation
- Expense editing (PUT endpoint)
- Multi-currency support
- Rate limiting middleware
- Dockerfile for backend containerization
- CI/CD pipeline with GitHub Actions
- Mobile-responsive frontend improvements
