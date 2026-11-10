import uuid
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    Column, String, Boolean, Date, Text, Integer, Numeric,
    ForeignKey, DateTime, Enum, UniqueConstraint, create_engine,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import enum

from config import DATABASE_URL

Base = declarative_base()

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Enums ----------

class RateType(str, enum.Enum):
    per_annum = "per_annum"
    per_month = "per_month"


class InterestType(str, enum.Enum):
    simple = "simple"
    compound = "compound"


# ---------- Models ----------

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(String(50), default="user")
    monthly_budget = Column(Numeric(12, 2), default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="user", cascade="all, delete-orphan")
    loans = relationship("Loan", back_populates="user", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_category_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    color = Column(String(20), nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="categories")
    expenses = relationship("Expense", back_populates="category", cascade="all, delete-orphan")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    date = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="expenses")
    category = relationship("Category", back_populates="expenses")


class Loan(Base):
    __tablename__ = "loans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    borrower_name = Column(String(255), nullable=False)
    borrower_phone = Column(String(50), nullable=True)
    borrower_email = Column(String(255), nullable=True)
    principal = Column(Numeric(14, 2), nullable=False)
    roi = Column(Numeric(6, 4), nullable=False)
    tenure_months = Column(Integer, nullable=True)  # Optional for simple interest
    rate_type = Column(Enum(RateType), nullable=False, default=RateType.per_annum)
    interest_type = Column(Enum(InterestType), nullable=False, default=InterestType.simple)
    monthly_payment = Column(Numeric(14, 2), nullable=True)
    total_interest = Column(Numeric(14, 2), nullable=True)
    loan_date = Column(Date, nullable=True)  # When loan was given
    end_date = Column(Date, nullable=True)   # Expected/actual end date
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="loans")
    payments = relationship("LoanPayment", back_populates="loan", cascade="all, delete-orphan")


class LoanPayment(Base):
    __tablename__ = "loan_payments"
    __table_args__ = (
        UniqueConstraint("loan_id", "month", "year", name="uq_loan_month_year"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    month = Column(Integer, nullable=False)  # 1-12
    year = Column(Integer, nullable=False)   # e.g. 2025
    amount_paid = Column(Numeric(14, 2), nullable=False)
    paid_date = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    loan = relationship("Loan", back_populates="payments")
    user = relationship("User")


def create_tables():
    """Create all tables in the database."""
    Base.metadata.create_all(bind=engine)
