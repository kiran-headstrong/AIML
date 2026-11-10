# Finance Manager — Product Requirements

## Project Overview

Finance Manager is a full-stack personal finance application that enables users to track expenses, manage budgets, organize spending by category, and monitor loans with interest calculations. The application provides a clean dashboard experience with data visualization and CSV export capabilities.

**Target Users:** Individuals who want a self-hosted, privacy-focused tool for managing personal finances without relying on third-party SaaS products.

---

## User Stories

### Authentication
- As a user, I want to register with my email and password so I can create a personal account.
- As a user, I want to log in and receive a JWT token so I can access my data securely.
- As a user, I want my session to persist for 24 hours so I don't have to log in repeatedly.

### Dashboard
- As a user, I want to see my monthly budget, total spending, and remaining balance at a glance.
- As a user, I want to see a breakdown of spending by category so I can identify where my money goes.
- As a user, I want to see my most recent expenses on the dashboard.

### Expenses
- As a user, I want to add an expense with an amount, date, category, and optional notes.
- As a user, I want to view my expenses filtered by month and year.
- As a user, I want to delete an expense if I entered it incorrectly.
- As a user, I want to export my expenses as a CSV file for record-keeping.

### Categories
- As a user, I want 5 default categories seeded when I register so I can start tracking immediately.
- As a user, I want to create custom categories with a name and color.
- As a user, I want to update or delete categories I no longer need.

### Budget
- As a user, I want to set a monthly budget so I can track how much I have left to spend.

### Loans
- As a user, I want to record a loan with borrower details, principal, interest rate, and tenure.
- As a user, I want to see calculated monthly payments and total interest.
- As a user, I want to view a full repayment schedule (amortization table) for any loan.
- As a user, I want to delete a loan record when it's been settled.

### UI/UX
- As a user, I want to toggle between dark and light themes.
- As a user, I want all my data scoped to my account so no one else can see it.

---

## Feature List

### P0 — Must Have (Core)
| Feature | Description |
|---------|-------------|
| User Registration | Email/password signup with bcrypt hashing |
| User Login | JWT-based authentication (HS256, 24h expiry) |
| Monthly Budget | Set and update monthly spending limit |
| Expense Tracking | CRUD operations on expenses with category linkage |
| Category Management | Create, update, delete color-coded categories |
| Dashboard | Budget summary, category breakdown, recent expenses |
| User Data Isolation | All queries scoped to authenticated user |

### P1 — Should Have (Important)
| Feature | Description |
|---------|-------------|
| Default Categories | 5 categories auto-seeded on registration |
| Expense Filtering | Filter expenses by month/year |
| CSV Export | Download expenses as CSV file |
| Loan Tracking | Record loans with interest calculations |
| Repayment Schedule | Generate amortization table (simple & compound) |
| Dark/Light Theme | UI theme toggle with persistence |

### P2 — Nice to Have (Future)
| Feature | Description |
|---------|-------------|
| Recurring Expenses | Auto-create expenses on a schedule |
| Expense Editing | Update existing expense records |
| Category Analytics | Historical trends per category |
| Multi-currency | Support for different currencies |
| Mobile Responsive | Optimized layout for mobile devices |
| Budget Alerts | Notifications when approaching budget limit |

---

## Scope

### In Scope
- Single-user and multi-user support (user-scoped data)
- RESTful API with OpenAPI/Swagger documentation
- PostgreSQL database with UUID primary keys
- Docker Compose for database provisioning
- pgAdmin for database management
- Single-page frontend (vanilla HTML/CSS/JS)
- JWT authentication with Bearer token scheme
- Simple and compound interest loan calculations

### Out of Scope
- Bank account integration / Plaid API
- OCR receipt scanning
- Multi-tenant organization support
- Mobile native applications (iOS/Android)
- Real-time notifications / WebSockets
- Two-factor authentication (2FA)
- Payment processing
- Shared budgets / household accounts

---

## Non-Functional Requirements

### Performance
- API response time < 200ms for standard CRUD operations
- Dashboard aggregation < 500ms for users with up to 10,000 expenses
- Database connection pooling via SQLAlchemy

### Security
- Passwords hashed with bcrypt (passlib)
- JWT tokens signed with HS256 algorithm
- Token expiration: 24 hours (configurable)
- All data endpoints require valid Bearer token
- User-scoped queries prevent cross-user data access
- CORS configured for local development

### Reliability
- PostgreSQL with volume persistence (Docker)
- Automatic table creation on application startup
- Health check on database container
- Graceful error handling with appropriate HTTP status codes

### Maintainability
- Modular route structure (auth, categories, expenses, loans, dashboard)
- Pydantic schemas for request/response validation
- Environment-based configuration (.env file)
- Type hints throughout Python codebase

---

## Success Criteria

1. A new user can register, log in, and see a functional dashboard within 30 seconds.
2. Users can add, view, filter, and export expenses without errors.
3. Loan repayment schedules calculate correctly for both simple and compound interest.
4. All API endpoints return proper error codes (401, 403, 404, 409, 422).
5. User A cannot access User B's data under any circumstance.
6. The application starts successfully with a single `docker-compose up -d && python backend/main.py` workflow.
7. API documentation is auto-generated and accessible at `/docs`.
