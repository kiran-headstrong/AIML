# Finance Manager — Implementation Checklist

## Phase 1: Project Setup

- [x] Initialize project directory structure
- [x] Create `docker-compose.yml` with PostgreSQL 15 and pgAdmin
- [x] Create `.env.example` with all required environment variables
- [x] Create `backend/requirements.txt` with dependencies
- [x] Create `backend/config.py` for environment-based configuration
- [x] Set up `.gitignore` for Python, Docker, and IDE files
- [x] Create `README.md` with setup instructions

## Phase 2: Backend Core

- [x] Create `backend/main.py` with FastAPI app initialization
- [x] Configure CORS middleware for local development
- [x] Create `backend/models.py` with SQLAlchemy Base and engine
- [x] Define `User` model with UUID primary key
- [x] Define `Category` model with user relationship and unique constraint
- [x] Define `Expense` model with user and category relationships
- [x] Define `Loan` model with rate/interest type enums
- [x] Implement `create_tables()` function for startup
- [x] Create `backend/schemas.py` with Pydantic request/response models
- [x] Implement database session dependency (`get_db`)

## Phase 3: Authentication

- [x] Create `backend/auth.py` with password hashing (bcrypt)
- [x] Implement `create_access_token()` with JWT (HS256, 24h expiry)
- [x] Implement `decode_token()` with error handling
- [x] Implement `get_current_user()` dependency (Bearer token)
- [x] Create `backend/routes/auth_routes.py`
- [x] Implement `POST /api/auth/register` with email uniqueness check
- [x] Seed 5 default categories on user registration
- [x] Implement `POST /api/auth/login` with password verification
- [x] Implement `GET /api/auth/me` for current user info

## Phase 4: Feature Routes

- [x] Create `backend/routes/category_routes.py`
- [x] Implement `GET /api/categories` (user-scoped)
- [x] Implement `POST /api/categories` with validation
- [x] Implement `PUT /api/categories/{id}` with ownership check
- [x] Implement `DELETE /api/categories/{id}` with ownership check
- [x] Create `backend/routes/expense_routes.py`
- [x] Implement `GET /api/expenses` with month/year filtering
- [x] Implement `POST /api/expenses` with category ownership verification
- [x] Implement `DELETE /api/expenses/{id}` with ownership check
- [x] Implement `GET /api/expenses/export` (CSV generation)
- [x] Create `backend/routes/loan_routes.py`
- [x] Implement `GET /api/loans` (user-scoped)
- [x] Implement `POST /api/loans` with interest calculations
- [x] Implement `DELETE /api/loans/{id}` with ownership check
- [x] Implement `GET /api/loans/{id}/schedule` (amortization table)
- [x] Create `backend/routes/dashboard_routes.py`
- [x] Implement `GET /api/dashboard` with aggregation queries
- [x] Implement `PUT /api/budget` to update monthly budget

## Phase 5: Frontend

- [x] Create `frontend/index.html` with page structure
- [x] Build login/register forms with validation
- [x] Implement JWT token storage in localStorage
- [x] Build dashboard view with budget display
- [x] Build category breakdown visualization
- [x] Build expenses table with month/year filter
- [x] Build add expense form with category dropdown
- [x] Build category management UI (create, edit, delete)
- [x] Build loan management page
- [x] Build loan repayment schedule view
- [x] Implement dark/light theme toggle
- [x] Implement CSV export download trigger
- [x] Add navigation between views
- [x] Handle 401 responses (redirect to login)

## Phase 6: Testing

- [ ] Set up pytest with test configuration
- [ ] Create test fixtures (test database, test client)
- [ ] Write unit tests for `auth.py` (hash, verify, token create/decode)
- [ ] Write unit tests for loan interest calculations
- [ ] Write integration tests for `/api/auth/register`
- [ ] Write integration tests for `/api/auth/login`
- [ ] Write integration tests for `/api/categories` CRUD
- [ ] Write integration tests for `/api/expenses` CRUD
- [ ] Write integration tests for `/api/expenses/export`
- [ ] Write integration tests for `/api/loans` CRUD
- [ ] Write integration tests for `/api/loans/{id}/schedule`
- [ ] Write integration tests for `/api/dashboard`
- [ ] Test user data isolation (user A can't see user B's data)
- [ ] Test edge cases (expired token, invalid UUID, zero budget)

## Phase 7: Deployment & Polish

- [ ] Create `Dockerfile` for backend service
- [ ] Add backend service to `docker-compose.yml`
- [ ] Set up production environment variables
- [ ] Add rate limiting middleware
- [ ] Add request logging middleware
- [ ] Create health check endpoint (`/health`)
- [ ] Write `CONTRIBUTING.md` with development guidelines
- [ ] Write `CHANGELOG.md` with version history
- [ ] Add `pyproject.toml` for project metadata and tooling
- [ ] Configure CI/CD pipeline (GitHub Actions)
- [ ] Add API versioning strategy
- [ ] Performance test with 10,000+ expense records
