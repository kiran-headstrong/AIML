import csv
import io
from uuid import UUID
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session

from models import Loan, LoanPayment, User, RateType, InterestType, get_db
from schemas import LoanCreate, LoanResponse, RepaymentScheduleEntry, LoanPaymentCreate, LoanPaymentResponse
from auth import get_current_user

router = APIRouter(prefix="/api/loans", tags=["Loans"])


def compute_loan_details(principal: Decimal, roi: Decimal, tenure_months: int,
                         rate_type: str, interest_type: str):
    """Compute monthly payment and total interest."""
    # Convert rate to monthly
    if rate_type == "per_annum":
        monthly_rate = roi / Decimal("12") / Decimal("100")
    else:
        monthly_rate = roi / Decimal("100")

    if interest_type == "simple":
        # Simple interest: borrower pays only interest monthly, principal at end
        if rate_type == "per_annum":
            total_interest = principal * (roi / Decimal("100")) * (Decimal(tenure_months) / Decimal("12"))
        else:
            total_interest = principal * monthly_rate * Decimal(tenure_months)
        monthly_payment = total_interest / Decimal(tenure_months)  # Only interest per month
    else:
        # Compound interest (EMI formula)
        if monthly_rate == 0:
            monthly_payment = principal / Decimal(tenure_months)
            total_interest = Decimal("0")
        else:
            # EMI = P * r * (1+r)^n / ((1+r)^n - 1)
            r = monthly_rate
            n = tenure_months
            factor = (1 + r) ** n
            monthly_payment = principal * r * factor / (factor - 1)
            total_interest = (monthly_payment * Decimal(n)) - principal

    monthly_payment = monthly_payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_interest = total_interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return monthly_payment, total_interest


def generate_schedule(principal: Decimal, roi: Decimal, tenure_months: int,
                      rate_type: str, interest_type: str) -> list[dict]:
    """Generate month-by-month repayment schedule."""
    if rate_type == "per_annum":
        monthly_rate = roi / Decimal("12") / Decimal("100")
    else:
        monthly_rate = roi / Decimal("100")

    monthly_payment, _ = compute_loan_details(
        principal, roi, tenure_months, rate_type, interest_type
    )

    schedule = []
    balance = principal

    for month in range(1, tenure_months + 1):
        if interest_type == "simple":
            interest = principal * monthly_rate
            interest = interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if month == tenure_months:
                # Last month: pay interest + full principal
                principal_component = principal
                payment = interest + principal
            else:
                # Regular months: interest only
                principal_component = Decimal("0")
                payment = interest
        else:
            interest = balance * monthly_rate
            interest = interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if month == tenure_months:
                principal_component = balance
                payment = balance + interest
            else:
                principal_component = monthly_payment - interest
                payment = monthly_payment

        principal_component = principal_component.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        payment = payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        closing = (balance - principal_component).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        schedule.append({
            "month": month,
            "opening_balance": float(balance),
            "interest": float(interest),
            "principal_component": float(principal_component),
            "payment": float(payment),
            "closing_balance": float(max(closing, Decimal("0"))),
        })

        balance = max(balance - principal_component, Decimal("0"))

    return schedule


# ==================== Loan Import ====================

@router.post("/import")
def import_loans_from_excel(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import loans from an Excel (.xlsx) or CSV file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    filename = file.filename.lower()
    if not (filename.endswith(".xlsx") or filename.endswith(".csv")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .csv files are supported")

    content = file.file.read()
    rows = []

    if filename.endswith(".csv"):
        text = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            rows.append(row)
    else:
        # Excel file
        from openpyxl import load_workbook
        wb = load_workbook(filename=io.BytesIO(content), read_only=True)
        ws = wb.active
        headers = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                headers = [str(h).strip().lower() if h else "" for h in row]
                continue
            row_dict = {}
            for j, val in enumerate(row):
                if j < len(headers) and headers[j]:
                    row_dict[headers[j]] = val
            rows.append(row_dict)
        wb.close()

    # Required fields
    required_fields = ["borrower_name", "principal", "roi", "tenure_months"]
    imported_count = 0

    for row in rows:
        # Check required fields
        if not all(row.get(f) for f in required_fields):
            continue

        try:
            principal = Decimal(str(row["principal"]))
            roi = Decimal(str(row["roi"]))
            tenure_months = int(row["tenure_months"])
            rate_type = str(row.get("rate_type", "per_annum")).strip().lower()
            interest_type = str(row.get("interest_type", "simple")).strip().lower()

            if rate_type not in ("per_annum", "per_month"):
                rate_type = "per_annum"
            if interest_type not in ("simple", "compound"):
                interest_type = "simple"

            if principal <= 0 or roi < 0 or tenure_months <= 0:
                continue

            monthly_payment, total_interest = compute_loan_details(
                principal, roi, tenure_months, rate_type, interest_type
            )

            loan = Loan(
                user_id=current_user.id,
                borrower_name=str(row["borrower_name"]).strip(),
                borrower_phone=str(row.get("borrower_phone", "") or "").strip() or None,
                borrower_email=str(row.get("borrower_email", "") or "").strip() or None,
                principal=principal,
                roi=roi,
                tenure_months=tenure_months,
                rate_type=RateType(rate_type),
                interest_type=InterestType(interest_type),
                monthly_payment=monthly_payment,
                total_interest=total_interest,
            )
            db.add(loan)
            imported_count += 1
        except (ValueError, InvalidOperation, TypeError):
            continue

    db.commit()
    return {"imported": imported_count, "total_rows": len(rows)}


# ==================== Loan CRUD ====================

@router.get("", response_model=list[LoanResponse])
def list_loans(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loans = (
        db.query(Loan)
        .filter(Loan.user_id == current_user.id)
        .order_by(Loan.created_at.desc())
        .all()
    )
    return [LoanResponse.model_validate(l) for l in loans]


@router.post("", response_model=LoanResponse, status_code=201)
def create_loan(
    data: LoanCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    monthly_payment = None
    total_interest = None

    # Only calculate if tenure is provided
    if data.tenure_months and data.tenure_months > 0:
        monthly_payment, total_interest = compute_loan_details(
            data.principal, data.roi, data.tenure_months,
            data.rate_type, data.interest_type,
        )
    elif data.interest_type == "simple":
        # For simple interest without tenure, calculate monthly interest only
        if data.rate_type == "per_annum":
            monthly_rate = data.roi / Decimal("12") / Decimal("100")
        else:
            monthly_rate = data.roi / Decimal("100")
        monthly_payment = (data.principal * monthly_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    loan = Loan(
        user_id=current_user.id,
        borrower_name=data.borrower_name,
        borrower_phone=data.borrower_phone,
        borrower_email=data.borrower_email,
        principal=data.principal,
        roi=data.roi,
        tenure_months=data.tenure_months,
        rate_type=RateType(data.rate_type),
        interest_type=InterestType(data.interest_type),
        monthly_payment=monthly_payment,
        total_interest=total_interest,
        loan_date=data.loan_date,
        end_date=data.end_date,
    )
    db.add(loan)
    db.commit()
    db.refresh(loan)
    return LoanResponse.model_validate(loan)


@router.delete("/{loan_id}", status_code=204)
def delete_loan(
    loan_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loan = (
        db.query(Loan)
        .filter(Loan.id == loan_id, Loan.user_id == current_user.id)
        .first()
    )
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    db.delete(loan)
    db.commit()
    return None


@router.put("/{loan_id}", response_model=LoanResponse)
def update_loan(
    loan_id: UUID,
    data: LoanCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loan = (
        db.query(Loan)
        .filter(Loan.id == loan_id, Loan.user_id == current_user.id)
        .first()
    )
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    monthly_payment = None
    total_interest = None

    if data.tenure_months and data.tenure_months > 0:
        monthly_payment, total_interest = compute_loan_details(
            data.principal, data.roi, data.tenure_months,
            data.rate_type, data.interest_type,
        )
    elif data.interest_type == "simple":
        if data.rate_type == "per_annum":
            monthly_rate = data.roi / Decimal("12") / Decimal("100")
        else:
            monthly_rate = data.roi / Decimal("100")
        monthly_payment = (data.principal * monthly_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    loan.borrower_name = data.borrower_name
    loan.borrower_phone = data.borrower_phone
    loan.borrower_email = data.borrower_email
    loan.principal = data.principal
    loan.roi = data.roi
    loan.tenure_months = data.tenure_months
    loan.rate_type = RateType(data.rate_type)
    loan.interest_type = InterestType(data.interest_type)
    loan.monthly_payment = monthly_payment
    loan.total_interest = total_interest
    loan.loan_date = data.loan_date
    loan.end_date = data.end_date

    db.commit()
    db.refresh(loan)
    return LoanResponse.model_validate(loan)


@router.get("/{loan_id}/schedule")
def get_repayment_schedule(
    loan_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loan = (
        db.query(Loan)
        .filter(Loan.id == loan_id, Loan.user_id == current_user.id)
        .first()
    )
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    schedule = generate_schedule(
        loan.principal, loan.roi, loan.tenure_months,
        loan.rate_type.value, loan.interest_type.value,
    )
    return {
        "loan_id": str(loan.id),
        "borrower_name": loan.borrower_name,
        "principal": float(loan.principal),
        "schedule": schedule,
    }


# ==================== Loan Payments ====================

@router.post("/{loan_id}/payments", response_model=LoanPaymentResponse, status_code=201)
def record_payment(
    loan_id: UUID,
    data: LoanPaymentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record a monthly interest payment for a loan."""
    loan = (
        db.query(Loan)
        .filter(Loan.id == loan_id, Loan.user_id == current_user.id)
        .first()
    )
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Check if payment already exists for this month/year
    existing = (
        db.query(LoanPayment)
        .filter(
            LoanPayment.loan_id == loan_id,
            LoanPayment.month == data.month,
            LoanPayment.year == data.year,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Payment already recorded for this month")

    payment = LoanPayment(
        loan_id=loan_id,
        user_id=current_user.id,
        month=data.month,
        year=data.year,
        amount_paid=data.amount_paid,
        paid_date=data.paid_date,
        notes=data.notes,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return LoanPaymentResponse.model_validate(payment)


@router.get("/{loan_id}/payments", response_model=list[LoanPaymentResponse])
def list_payments(
    loan_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all payments for a loan."""
    loan = (
        db.query(Loan)
        .filter(Loan.id == loan_id, Loan.user_id == current_user.id)
        .first()
    )
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    payments = (
        db.query(LoanPayment)
        .filter(LoanPayment.loan_id == loan_id)
        .order_by(LoanPayment.year.desc(), LoanPayment.month.desc())
        .all()
    )
    return [LoanPaymentResponse.model_validate(p) for p in payments]


@router.delete("/{loan_id}/payments/{payment_id}", status_code=204)
def delete_payment(
    loan_id: UUID,
    payment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a payment (undo)."""
    payment = (
        db.query(LoanPayment)
        .filter(
            LoanPayment.id == payment_id,
            LoanPayment.loan_id == loan_id,
            LoanPayment.user_id == current_user.id,
        )
        .first()
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    db.delete(payment)
    db.commit()
    return None


@router.get("/{loan_id}/payment-status")
def get_payment_status(
    loan_id: UUID,
    year: int = Query(..., ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get payment status for a loan by year (shows which months are paid)."""
    loan = (
        db.query(Loan)
        .filter(Loan.id == loan_id, Loan.user_id == current_user.id)
        .first()
    )
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    payments = (
        db.query(LoanPayment)
        .filter(LoanPayment.loan_id == loan_id, LoanPayment.year == year)
        .all()
    )

    paid_months = {}
    for p in payments:
        paid_months[p.month] = {
            "id": str(p.id),
            "amount_paid": float(p.amount_paid),
            "paid_date": str(p.paid_date),
            "notes": p.notes,
        }

    months_status = []
    for m in range(1, 13):
        if m in paid_months:
            months_status.append({"month": m, "paid": True, **paid_months[m]})
        else:
            months_status.append({"month": m, "paid": False})

    paid_count = len(paid_months)
    return {
        "loan_id": str(loan_id),
        "year": year,
        "paid_count": paid_count,
        "total_months": 12,
        "monthly_interest": float(loan.monthly_payment),
        "months": months_status,
    }
