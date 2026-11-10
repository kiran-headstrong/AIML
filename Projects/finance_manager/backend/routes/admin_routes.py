"""Admin-only routes. Requires role='admin' on the authenticated user."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from models import User, Expense, Category, Loan, get_db
from schemas import UserResponse
from auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency that ensures the current user has admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


@router.get("/users", response_model=List[UserResponse])
def list_all_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all registered users (admin only)."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [UserResponse.model_validate(u) for u in users]


@router.get("/stats")
def system_stats(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get system-wide statistics (admin only)."""
    total_users = db.query(User).count()
    total_expenses = db.query(Expense).count()
    total_categories = db.query(Category).count()
    total_loans = db.query(Loan).count()

    return {
        "total_users": total_users,
        "total_expenses": total_expenses,
        "total_categories": total_categories,
        "total_loans": total_loans,
    }


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a user and all their data (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if str(user.id) == str(admin.id):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    db.delete(user)
    db.commit()
    return {"detail": f"User {user.email} deleted"}
