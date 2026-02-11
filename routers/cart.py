from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from schemas import CartItemBase, CartItemOut, Checkout
from models import CartItem, User
from auth import get_current_user_or_none

router = APIRouter(prefix="/cart", tags=["Корзина"])


@router.post("/")
def add_to_cart(
    item: CartItemBase,
    current_user: Optional[User] = Depends(get_current_user_or_none),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    # Определяем, по какому полю ищем существующую запись
    if current_user:
        filter_field = CartItem.user_id == current_user.id
    else:
        if not session_id:
            raise HTTPException(status_code=400, detail="Для неавторизованных нужен session_id")
        filter_field = CartItem.session_id == session_id

    # Ищем существующую запись с таким же product_id
    existing_item = (
        db.query(CartItem)
        .filter(filter_field)
        .filter(CartItem.product_id == item.product_id)
        .first()
    )

    if existing_item:
        # Если товар уже в корзине — увеличиваем количество
        existing_item.quantity += item.quantity  # или += 1, если всегда добавляем по 1
        db.commit()
        return {"id": existing_item.id, "message": "Количество увеличено"}
    else:
        # Если товара ещё нет — создаём новую запись
        if current_user:
            cart_item = CartItem(user_id=current_user.id, **item.dict())
        else:
            cart_item = CartItem(session_id=session_id, **item.dict())
        db.add(cart_item)
        db.commit()
        db.refresh(cart_item)
        return {"id": cart_item.id, "message": "Товар добавлен"}


@router.get("/", response_model=List[CartItemOut])
def get_cart(
    current_user: Optional[User] = Depends(get_current_user_or_none),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if current_user:
        return db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    else:
        if not session_id:
            raise HTTPException(400, "Для неавторизованных нужен session_id")
        return db.query(CartItem).filter(CartItem.session_id == session_id).all()


@router.delete("/{item_id}")
def delete_cart_item(
    item_id: int,
    current_user: Optional[User] = Depends(get_current_user_or_none),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if current_user:
        item = (
            db.query(CartItem)
            .filter(CartItem.id == item_id, CartItem.user_id == current_user.id)
            .first()
        )
    else:
        if not session_id:
            raise HTTPException(400, "session_id обязателен")
        item = (
            db.query(CartItem)
            .filter(CartItem.id == item_id, CartItem.session_id == session_id)
            .first()
        )
    if not item:
        raise HTTPException(404, "Элемент не найден")
    db.delete(item)
    db.commit()
    return {"message": "Удалено"}


@router.post("/checkout/")
def checkout(
    checkout_data: Checkout,
    current_user: Optional[User] = Depends(get_current_user_or_none),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if current_user:
        address = checkout_data.delivery_address or current_user.delivery_address
        if checkout_data.delivery_address:
            current_user.delivery_address = checkout_data.delivery_address
            db.commit()
        items = db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    else:
        if not session_id:
            raise HTTPException(400, "session_id обязателен")
        address = checkout_data.delivery_address
        if not address:
            raise HTTPException(400, "Адрес обязателен для гостей")
        items = db.query(CartItem).filter(CartItem.session_id == session_id).all()

    for item in items:
        db.delete(item)
    db.commit()

    return {"message": "Заказ оформлен (корзина очищена)", "address": address}

@router.post("/update")
def update_cart_item(
    data: dict,
    current_user: Optional[User] = Depends(get_current_user_or_none),
    db: Session = Depends(get_db)
):
    item_id = data.get("item_id")
    new_quantity = data.get("quantity")
    session_id = data.get("session_id")

    if not item_id or not new_quantity:
        raise HTTPException(400, "Не указаны item_id или quantity")

    if current_user:
        item = db.query(CartItem).filter(
            CartItem.id == item_id,
            CartItem.user_id == current_user.id
        ).first()
    else:
        if not session_id:
            raise HTTPException(400, "session_id обязателен")
        item = db.query(CartItem).filter(
            CartItem.id == item_id,
            CartItem.session_id == session_id
        ).first()

    if not item:
        raise HTTPException(404, "Элемент не найден")

    item.quantity = max(1, new_quantity)  # минимум 1
    db.commit()
    return {"message": "Количество обновлено"}