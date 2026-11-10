from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from models import User, Category, get_db
from schemas import UserRegister, UserLogin, UserResponse, TokenResponse
from auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Default categories seeded for every new user
DEFAULT_CATEGORIES = [
    {"name": "Food & Dining", "color": "#FF6384"},
    {"name": "Transportation", "color": "#36A2EB"},
    {"name": "Housing & Rent", "color": "#FFCE56"},
    {"name": "Entertainment", "color": "#4BC0C0"},
    {"name": "Utilities", "color": "#9966FF"},
]


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(data: UserRegister, db: Session = Depends(get_db)):
    # Check if email already exists
    existing = db.query(User).filter(User.email == data.email.lower().strip()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=data.email.lower().strip(),
        password_hash=hash_password(data.password),
        name=data.name.strip(),
    )
    db.add(user)
    db.flush()  # Get user.id before creating categories

    # Seed default categories
    for cat in DEFAULT_CATEGORIES:
        category = Category(
            user_id=user.id,
            name=cat["name"],
            color=cat["color"],
            is_default=True,
        )
        db.add(category)

    db.commit()
    db.refresh(user)

    # Generate token
    token = create_access_token(str(user.id), user.email)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email.lower().strip()).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(str(user.id), user.email)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)
