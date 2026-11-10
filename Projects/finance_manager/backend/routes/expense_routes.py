import csv
import io
from uuid import UUID
from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import extract

from models import Expense, Category, User, get_db
from schemas import ExpenseCreate, ExpenseResponse
from auth import get_current_user

router = APIRouter(prefix="/api/expenses", tags=["Expenses"])


@router.get("", response_model=list[ExpenseResponse])
def list_expenses(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Expense).filter(Expense.user_id == current_user.id)

    if month is not None:
        query = query.filter(extract("month", Expense.date) == month)
    if year is not None:
        query = query.filter(extract("year", Expense.date) == year)

    expenses = query.order_by(Expense.date.desc()).all()

    results = []
    for exp in expenses:
        resp = ExpenseResponse(
            id=exp.id,
            amount=exp.amount,
            category_id=exp.category_id,
            category_name=exp.category.name if exp.category else None,
            category_color=exp.category.color if exp.category else None,
            date=exp.date,
            notes=exp.notes,
            created_at=exp.created_at,
        )
        results.append(resp)
    return results


@router.post("", response_model=ExpenseResponse, status_code=201)
def create_expense(
    data: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify category belongs to user
    category = (
        db.query(Category)
        .filter(Category.id == data.category_id, Category.user_id == current_user.id)
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    expense = Expense(
        user_id=current_user.id,
        category_id=data.category_id,
        amount=data.amount,
        date=data.date,
        notes=data.notes,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)

    return ExpenseResponse(
        id=expense.id,
        amount=expense.amount,
        category_id=expense.category_id,
        category_name=category.name,
        category_color=category.color,
        date=expense.date,
        notes=expense.notes,
        created_at=expense.created_at,
    )


@router.delete("/{expense_id}", status_code=204)
def delete_expense(
    expense_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    db.delete(expense)
    db.commit()
    return None


@router.put("/{expense_id}", response_model=ExpenseResponse)
def update_expense(
    expense_id: UUID,
    data: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    # Verify category belongs to user
    category = (
        db.query(Category)
        .filter(Category.id == data.category_id, Category.user_id == current_user.id)
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    expense.amount = data.amount
    expense.category_id = data.category_id
    expense.date = data.date
    expense.notes = data.notes
    db.commit()
    db.refresh(expense)

    return ExpenseResponse(
        id=expense.id,
        amount=expense.amount,
        category_id=expense.category_id,
        category_name=category.name,
        category_color=category.color,
        date=expense.date,
        notes=expense.notes,
        created_at=expense.created_at,
    )


@router.get("/export")
def export_expenses(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Expense).filter(Expense.user_id == current_user.id)

    if month is not None:
        query = query.filter(extract("month", Expense.date) == month)
    if year is not None:
        query = query.filter(extract("year", Expense.date) == year)

    expenses = query.order_by(Expense.date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Category", "Amount", "Notes"])

    for exp in expenses:
        writer.writerow([
            exp.date.isoformat(),
            exp.category.name if exp.category else "Unknown",
            str(exp.amount),
            exp.notes or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=expenses.csv"},
    )
