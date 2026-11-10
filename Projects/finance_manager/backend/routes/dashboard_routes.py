from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from models import Expense, Category, User, get_db
from schemas import DashboardResponse, ExpenseResponse, BudgetUpdate
from auth import get_current_user

router = APIRouter(prefix="/api", tags=["Dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    current_month = today.month
    current_year = today.year

    # Total spent this month
    total_spent = (
        db.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == current_user.id,
            extract("month", Expense.date) == current_month,
            extract("year", Expense.date) == current_year,
        )
        .scalar()
    )
    total_spent = Decimal(str(total_spent))

    # Category breakdown for current month
    category_breakdown_query = (
        db.query(
            Category.name,
            Category.color,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .outerjoin(
            Expense,
            (Expense.category_id == Category.id)
            & (extract("month", Expense.date) == current_month)
            & (extract("year", Expense.date) == current_year),
        )
        .filter(Category.user_id == current_user.id)
        .group_by(Category.id, Category.name, Category.color)
        .all()
    )

    category_breakdown = [
        {"name": row.name, "color": row.color, "total": float(row.total)}
        for row in category_breakdown_query
        if float(row.total) > 0
    ]

    # Recent expenses (last 10)
    recent = (
        db.query(Expense)
        .filter(Expense.user_id == current_user.id)
        .order_by(Expense.date.desc())
        .limit(10)
        .all()
    )

    recent_expenses = [
        ExpenseResponse(
            id=exp.id,
            amount=exp.amount,
            category_id=exp.category_id,
            category_name=exp.category.name if exp.category else None,
            category_color=exp.category.color if exp.category else None,
            date=exp.date,
            notes=exp.notes,
            created_at=exp.created_at,
        )
        for exp in recent
    ]

    # Counts
    total_categories = (
        db.query(func.count(Category.id))
        .filter(Category.user_id == current_user.id)
        .scalar()
    )
    total_expenses = (
        db.query(func.count(Expense.id))
        .filter(Expense.user_id == current_user.id)
        .scalar()
    )

    budget = current_user.monthly_budget or Decimal("0")
    balance = budget - total_spent

    return DashboardResponse(
        monthly_budget=budget,
        total_spent_this_month=total_spent,
        balance=balance,
        total_categories=total_categories,
        total_expenses=total_expenses,
        recent_expenses=recent_expenses,
        category_breakdown=category_breakdown,
    )


@router.put("/budget")
def update_budget(
    data: BudgetUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.monthly_budget = data.amount
    db.commit()
    db.refresh(current_user)
    return {"monthly_budget": float(current_user.monthly_budget)}
