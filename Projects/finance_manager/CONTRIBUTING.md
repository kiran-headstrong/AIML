# Contributing to Finance Manager

Thank you for contributing! This guide covers the workflow, coding standards, and requirements for submitting changes.

---

## Git Branching Strategy

```
main          ← production-ready code (protected)
  └── develop ← integration branch for features
        ├── feature/expense-editing
        ├── feature/recurring-expenses
        └── fix/loan-calculation-rounding
```

| Branch | Purpose | Merges Into |
|--------|---------|-------------|
| `main` | Stable releases only | — |
| `develop` | Integration & testing | `main` (via PR) |
| `feature/*` | New features | `develop` |
| `fix/*` | Bug fixes | `develop` |
| `hotfix/*` | Critical production fixes | `main` + `develop` |

---

## Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no logic change |
| `refactor` | Code restructuring, no feature change |
| `test` | Adding or updating tests |
| `chore` | Build scripts, CI, tooling |

### Scopes

Use: `auth`, `expenses`, `categories`, `loans`, `dashboard`, `frontend`, `db`, `config`

### Examples

```
feat(expenses): add CSV export with date filtering
fix(auth): handle expired token gracefully on /me endpoint
docs(readme): update quick start instructions
test(loans): add compound interest schedule tests
```

---

## Pull Request Checklist

Before submitting a PR, verify:

- [ ] Branch is up-to-date with `develop`
- [ ] Code passes `ruff check backend/` with no errors
- [ ] Code is formatted with `black backend/`
- [ ] All existing tests pass: `pytest`
- [ ] New features include corresponding tests
- [ ] API changes are reflected in schema files
- [ ] No hardcoded secrets or credentials in code
- [ ] Pydantic schemas validate all new request/response bodies
- [ ] User data isolation is maintained (queries scoped by user_id)

### PR Title Format

Same as commit messages:
```
feat(expenses): add monthly expense summary endpoint
```

### PR Description Template

```markdown
## Summary
Brief description of what this PR does.

## Changes
- Added/Modified/Removed X
- Updated Y schema

## Testing
- [ ] Unit tests added
- [ ] Integration tests added
- [ ] Manual testing performed

## Related Issues
Closes #123
```

---

## Code Style

### Python (Backend)

- **Linter:** Ruff (`ruff check backend/`)
- **Formatter:** Black (`black backend/ --line-length 100`)
- **Line length:** 100 characters
- **Python version:** 3.10+
- **Type hints:** Required on all function signatures
- **Docstrings:** Required on modules and complex functions

### Key Conventions

```python
# Route functions: descriptive names
@router.get("/api/expenses")
def list_expenses(...)

# Dependencies: use FastAPI Depends
def get_expenses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

# Schemas: separate Create/Update/Response models
class ExpenseCreate(BaseModel): ...
class ExpenseResponse(BaseModel): ...

# Models: SQLAlchemy declarative with relationships
class Expense(Base):
    __tablename__ = "expenses"
```

### Frontend

- Vanilla HTML/CSS/JS (no build tools)
- Use `fetch()` for API calls
- Store JWT in `localStorage`
- Consistent naming: `camelCase` for JS, `kebab-case` for CSS classes

---

## Testing Requirements

### Before Merge

1. All tests pass: `pytest`
2. No regressions in existing functionality
3. Coverage does not decrease below 80%

### Writing Tests

```python
# tests/test_auth.py
import pytest
from httpx import AsyncClient

@pytest.mark.integration
async def test_register_creates_user_and_default_categories(client: AsyncClient):
    response = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "secure123",
        "name": "Test User",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "test@example.com"
```

### Test Database

Tests should use a separate PostgreSQL database or SQLite in-memory to avoid polluting development data.

---

## Development Setup

```bash
# 1. Clone and enter project
git clone <repo-url>
cd finance_manager

# 2. Start database
docker-compose up -d

# 3. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# 4. Install dependencies
pip install -r backend/requirements.txt
pip install ruff black pytest httpx pytest-cov

# 5. Copy environment file
cp .env.example .env

# 6. Run the app
cd backend && python main.py

# 7. Run tests
pytest

# 8. Lint and format
ruff check backend/
black backend/
```

---

## Questions?

Open an issue or start a discussion. All contributions — bug reports, feature requests, documentation improvements — are welcome.
