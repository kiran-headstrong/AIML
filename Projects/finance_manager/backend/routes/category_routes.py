from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from models import Category, User, get_db
from schemas import CategoryCreate, CategoryUpdate, CategoryResponse
from auth import get_current_user

router = APIRouter(prefix="/api/categories", tags=["Categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    categories = (
        db.query(Category)
        .filter(Category.user_id == current_user.id)
        .order_by(Category.created_at)
        .all()
    )
    return [CategoryResponse.model_validate(c) for c in categories]


@router.post("", response_model=CategoryResponse, status_code=201)
def create_category(
    data: CategoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Check for duplicate name
    existing = (
        db.query(Category)
        .filter(Category.user_id == current_user.id, Category.name == data.name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Category with this name already exists")

    category = Category(
        user_id=current_user.id,
        name=data.name,
        color=data.color,
        is_default=data.is_default,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return CategoryResponse.model_validate(category)


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == current_user.id)
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    if data.name is not None:
        # Check duplicate
        dup = (
            db.query(Category)
            .filter(
                Category.user_id == current_user.id,
                Category.name == data.name,
                Category.id != category_id,
            )
            .first()
        )
        if dup:
            raise HTTPException(status_code=409, detail="Category name already exists")
        category.name = data.name

    if data.color is not None:
        category.color = data.color

    db.commit()
    db.refresh(category)
    return CategoryResponse.model_validate(category)


@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == current_user.id)
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    db.delete(category)
    db.commit()
    return None
