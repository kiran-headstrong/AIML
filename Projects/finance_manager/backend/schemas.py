from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


# ---------- Auth ----------

class UserRegister(BaseModel):
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=6)
    name: str = Field(..., min_length=1)


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str
    role: str
    monthly_budget: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ---------- Budget ----------

class BudgetUpdate(BaseModel):
    amount: Decimal = Field(..., ge=0)


# ---------- Categories ----------

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field(..., min_length=3, max_length=20)
    is_default: bool = False


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = Field(None, min_length=3, max_length=20)


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    color: str
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Expenses ----------

class ExpenseCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    category_id: UUID
    date: date
    notes: Optional[str] = None


class ExpenseResponse(BaseModel):
    id: UUID
    amount: Decimal
    category_id: UUID
    category_name: Optional[str] = None
    category_color: Optional[str] = None
    date: date
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Loans ----------

class LoanCreate(BaseModel):
    borrower_name: str = Field(..., min_length=1)
    borrower_phone: Optional[str] = None
    borrower_email: Optional[str] = None
    principal: Decimal = Field(..., gt=0)
    roi: Decimal = Field(..., ge=0)
    tenure_months: Optional[int] = None  # Optional for simple interest
    rate_type: str = "per_annum"
    interest_type: str = "simple"
    loan_date: Optional[date] = None  # When loan was given
    end_date: Optional[date] = None   # Expected end date


class LoanResponse(BaseModel):
    id: UUID
    borrower_name: str
    borrower_phone: Optional[str]
    borrower_email: Optional[str]
    principal: Decimal
    roi: Decimal
    tenure_months: Optional[int]
    rate_type: str
    interest_type: str
    monthly_payment: Optional[Decimal]
    total_interest: Optional[Decimal]
    loan_date: Optional[date]
    end_date: Optional[date]
    created_at: datetime

    class Config:
        from_attributes = True


class RepaymentScheduleEntry(BaseModel):
    month: int
    opening_balance: Decimal
    interest: Decimal
    principal_component: Decimal
    payment: Decimal
    closing_balance: Decimal


# ---------- Dashboard ----------

class DashboardResponse(BaseModel):
    monthly_budget: Decimal
    total_spent_this_month: Decimal
    balance: Decimal
    total_categories: int
    total_expenses: int
    recent_expenses: List[ExpenseResponse]
    category_breakdown: List[dict]


# ---------- Loan Payments ----------

class LoanPaymentCreate(BaseModel):
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2000, le=2100)
    amount_paid: Decimal = Field(..., gt=0)
    paid_date: date
    notes: Optional[str] = None


class LoanPaymentResponse(BaseModel):
    id: UUID
    loan_id: UUID
    month: int
    year: int
    amount_paid: Decimal
    paid_date: date
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
