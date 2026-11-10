"""
Finance Manager - FastAPI Backend
Run: python backend/main.py
"""
import sys
from pathlib import Path

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import HTTPException
import uvicorn

from config import BACKEND_HOST, BACKEND_PORT
from models import create_tables

# Import routers
from routes.auth_routes import router as auth_router
from routes.category_routes import router as category_router
from routes.expense_routes import router as expense_router
from routes.loan_routes import router as loan_router
from routes.dashboard_routes import router as dashboard_router
from routes.admin_routes import router as admin_router

# Create FastAPI app
app = FastAPI(
    title="Finance Manager API",
    description="Personal finance management API with JWT authentication",
    version="1.0.0",
)

# CORS - allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(category_router)
app.include_router(expense_router)
app.include_router(loan_router)
app.include_router(dashboard_router)
app.include_router(admin_router)


@app.get("/")
def root():
    """Serve the frontend UI."""
    frontend_path = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    if frontend_path.exists():
        return FileResponse(str(frontend_path))
    return {
        "message": "Finance Manager API",
        "docs": "/docs",
        "version": "1.0.0",
    }


@app.get("/sample_loan_import.csv")
def download_sample_csv():
    """Serve the sample loan import template."""
    csv_path = Path(__file__).resolve().parent.parent / "sample_loan_import.csv"
    if csv_path.exists():
        return FileResponse(str(csv_path), media_type="text/csv", filename="sample_loan_import.csv")
    raise HTTPException(status_code=404, detail="Sample file not found")


@app.on_event("startup")
def on_startup():
    """Create database tables and seed admin user on startup."""
    create_tables()
    print("✓ Database tables created/verified")
    seed_admin_user()


def seed_admin_user():
    """Create default admin user if not exists."""
    from models import User, Category, SessionLocal
    from auth import hash_password

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == "admin@financemanager.com").first()
        if not existing:
            admin = User(
                email="admin@financemanager.com",
                password_hash=hash_password("admin123"),
                name="Admin",
                role="admin",
                monthly_budget=10000,
            )
            db.add(admin)
            db.flush()

            # Seed default categories for admin
            default_cats = [
                {"name": "Food & Dining", "color": "#FF6384"},
                {"name": "Transportation", "color": "#36A2EB"},
                {"name": "Housing & Rent", "color": "#FFCE56"},
                {"name": "Entertainment", "color": "#4BC0C0"},
                {"name": "Utilities", "color": "#9966FF"},
            ]
            for cat in default_cats:
                db.add(Category(user_id=admin.id, name=cat["name"], color=cat["color"], is_default=True))

            db.commit()
            print("✓ Default admin user created (admin@financemanager.com / admin123)")
        else:
            print("✓ Admin user already exists")
    finally:
        db.close()


if __name__ == "__main__":
    print(f"🚀 Starting Finance Manager API on http://{BACKEND_HOST}:{BACKEND_PORT}")
    print(f"📖 API Docs: http://localhost:{BACKEND_PORT}/docs")
    uvicorn.run(
        "main:app",
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        reload=True,
    )
