from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user_or_none
from database import get_db
from models import Product, User
from recommendations import RecommendationService
from routers.cart import get_cart
from schemas import ProductOut

router = APIRouter(prefix="/api/recommendations", tags=["Рекомендации"])
service = RecommendationService()


class RecommendationProductOut(ProductOut):
    reason: Optional[str] = None


class RecommendationBlockOut(BaseModel):
    placement: str
    products: List[RecommendationProductOut]


class RecommendationHomeOut(BaseModel):
    popular: RecommendationBlockOut
    recommend_now: RecommendationBlockOut
    for_you: RecommendationBlockOut


def to_products_with_reason(products: List[Product], reason: str | None = None) -> List[RecommendationProductOut]:
    result = []
    for product in products:
        payload = ProductOut.model_validate(product, from_attributes=True).model_dump()
        result.append(RecommendationProductOut(**payload, reason=reason))
    return result


def to_products_with_personal_reasons(recs: list[tuple[Product, str]]) -> List[RecommendationProductOut]:
    result = []
    for product, reason in recs:
        payload = ProductOut.model_validate(product, from_attributes=True).model_dump()
        result.append(RecommendationProductOut(**payload, reason=reason))
    return result


@router.get("/home", response_model=RecommendationHomeOut)
def home_recommendations(
    session_id: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_or_none),
    db: Session = Depends(get_db),
):
    popular = service.get_popular_products(db, limit=6)
    rec_now_with_reasons = service.get_user_recs_with_reasons(db, user=current_user, session_id=session_id, limit=6)
    for_you_with_reasons = service.get_user_recs_with_reasons(db, user=current_user, session_id=session_id, limit=6) if current_user else []

    return RecommendationHomeOut(
        popular=RecommendationBlockOut(
            placement="home_popular",
            products=to_products_with_reason(popular, reason="Высокая популярность"),
        ),
        recommend_now=RecommendationBlockOut(
            placement="home_now",
            products=to_products_with_personal_reasons(rec_now_with_reasons),
        ),
        for_you=RecommendationBlockOut(
            placement="home_for_you",
            products=to_products_with_personal_reasons(for_you_with_reasons),
        ),
    )


@router.get("/product/{product_id}", response_model=RecommendationBlockOut)
def product_recommendations(
    product_id: int,
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    recs = service.get_product_recs(db, product=product, limit=6)
    return RecommendationBlockOut(
        placement="product_also_buy",
        products=to_products_with_reason(recs, reason="Та же категория и/или близкое КБЖУ"),
    )


@router.get("/cart", response_model=RecommendationBlockOut)
def cart_recommendations(
    session_id: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_or_none),
    db: Session = Depends(get_db),
):
    cart_items = get_cart(current_user=current_user, session_id=session_id, db=db)
    recs = service.get_cart_recs(db, cart_items=cart_items, limit=6)
    return RecommendationBlockOut(
        placement="cart_complete_order",
        products=to_products_with_reason(recs, reason="Похоже на состав вашей корзины"),
    )


@router.get("/user", response_model=RecommendationBlockOut)
def user_recommendations(
    session_id: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_or_none),
    db: Session = Depends(get_db),
):
    recs_with_reasons = service.get_user_recs_with_reasons(db, user=current_user, session_id=session_id, limit=6)
    return RecommendationBlockOut(
        placement="home_for_you",
        products=to_products_with_personal_reasons(recs_with_reasons),
    )
