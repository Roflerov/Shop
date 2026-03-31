from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from ml_dataset import sync_order_with_training_interactions
from schemas import CartItemBase, CartItemOut, Checkout, CartUpdateRequest
from models import CartItem, User, Product, Order, OrderItem
from auth import get_current_user_or_none
from recommendations import log_recommendation_event
import time

router = APIRouter(prefix="/cart", tags=["Корзина"])


def add_to_cart_internal(db: Session, product_id: int, quantity: int = 1, user: Optional[User] = None, session_id: Optional[str] = None):
    """Внутренняя функция для добавления товара в корзину из других роутеров.
    Возвращает dict с id и message (аналогично API).
    """
    if user:
        filter_field = CartItem.user_id == user.id
    else:
        if not session_id:
            # Ничего не делаем, но возвращаем сообщение об ошибке — вызывающий код может решить, что делать
            return {"error": "session_id required for anonymous users"}
        filter_field = CartItem.session_id == session_id

    existing_item = (
        db.query(CartItem)
        .filter(filter_field)
        .filter(CartItem.product_id == product_id)
        .first()
    )

    if existing_item:
        existing_item.quantity += quantity
        db.query(Product).filter(Product.id == product_id).update(
            {Product.popularity: Product.popularity + max(1, quantity)}, synchronize_session=False
        )
        db.commit()
        return {"id": existing_item.id, "message": "Количество увеличено"}
    else:
        data = {"product_id": product_id, "quantity": quantity}
        if user:
            cart_item = CartItem(user_id=user.id, **data)
        else:
            cart_item = CartItem(session_id=session_id, **data)
        db.add(cart_item)
        db.query(Product).filter(Product.id == product_id).update(
            {Product.popularity: Product.popularity + max(1, quantity)}, synchronize_session=False
        )
        db.commit()
        db.refresh(cart_item)
        return {"id": cart_item.id, "message": "Товар добавлен"}


@router.post("/")
def add_to_cart(
    item: CartItemBase,
    current_user: Optional[User] = Depends(get_current_user_or_none),
    session_id: Optional[str] = Query(None),
    rec_source: Optional[str] = Query(None),
    rec_origin_product_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    if current_user:
        filter_field = CartItem.user_id == current_user.id
        rec_user_id = current_user.id
        rec_session_id = None
    else:
        if not session_id:
            raise HTTPException(400, "session_id обязателен для гостя")
        filter_field = CartItem.session_id == session_id
        rec_user_id = None
        rec_session_id = session_id

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
        db.query(Product).filter(Product.id == item.product_id).update(
            {Product.popularity: Product.popularity + max(1, item.quantity)}, synchronize_session=False
        )
        db.commit()
        if rec_source:
            log_recommendation_event(
                db=db,
                placement=rec_source,
                event_type="add_to_cart",
                product_id=item.product_id,
                user_id=rec_user_id,
                session_id=rec_session_id,
                source_product_id=rec_origin_product_id,
            )
            db.commit()
        return {"id": existing_item.id, "message": "Количество увеличено"}
    else:
        # Если товара ещё нет — создаём новую запись
        if current_user:
            cart_item = CartItem(user_id=current_user.id, **item.dict())
        else:
            cart_item = CartItem(session_id=session_id, **item.dict())
        db.add(cart_item)
        db.query(Product).filter(Product.id == item.product_id).update(
            {Product.popularity: Product.popularity + max(1, item.quantity)}, synchronize_session=False
        )
        db.commit()
        db.refresh(cart_item)
        if rec_source:
            log_recommendation_event(
                db=db,
                placement=rec_source,
                event_type="add_to_cart",
                product_id=item.product_id,
                user_id=rec_user_id,
                session_id=rec_session_id,
                source_product_id=rec_origin_product_id,
            )
            db.commit()
        return {"id": cart_item.id, "message": "Товар добавлен"}


@router.get("/", response_model=List[CartItemOut])
def get_cart(
    current_user: Optional[User] = Depends(get_current_user_or_none),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    base_query = db.query(CartItem).join(Product, Product.id == CartItem.product_id)
    if current_user:
        return base_query.filter(CartItem.user_id == current_user.id).all()
    if not session_id:
        raise HTTPException(400, "session_id обязателен для гостя")
    return base_query.filter(CartItem.session_id == session_id).all()


@router.delete("/{item_id}")
def delete_cart_item(
    item_id: int,
    current_user: Optional[User] = Depends(get_current_user_or_none),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(CartItem).filter(CartItem.id == item_id)
    if current_user:
        query = query.filter(CartItem.user_id == current_user.id)
    else:
        if not session_id:
            raise HTTPException(400, "session_id обязателен для гостя")
        query = query.filter(CartItem.session_id == session_id)
    item = query.first()
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
    else:
        address = checkout_data.delivery_address
    if current_user and checkout_data.delivery_address:
        current_user.delivery_address = checkout_data.delivery_address
        db.commit()

    cart_query = db.query(CartItem).join(Product, Product.id == CartItem.product_id)
    if current_user:
        items = cart_query.filter(CartItem.user_id == current_user.id).all()
        user_id = current_user.id
        guest_session_id = None
    else:
        if not session_id:
            raise HTTPException(400, "session_id обязателен для гостя")
        items = cart_query.filter(CartItem.session_id == session_id).all()
        user_id = None
        guest_session_id = session_id

    if not items:
        raise HTTPException(400, "Корзина пуста")

    ts = int(time.time())
    total = sum(item.product.price * item.quantity for item in items)
    order = Order(
        user_id=user_id,
        session_id=guest_session_id,
        status="created",
        total=total,
        delivery_address=address,
        created_at=ts,
    )
    db.add(order)
    db.flush()

    created_order_items = []
    for item in items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            quantity=max(1, int(item.quantity)),
            unit_price=float(item.product.price),
            created_at=ts,
        )
        db.add(order_item)
        created_order_items.append(order_item)

    for item in items:
        db.delete(item)

    sync_order_with_training_interactions(db=db, order=order, order_items=created_order_items)
    db.commit()

    return {"message": "Заказ оформлен (корзина очищена)", "address": address, "order_id": order.id}

@router.post("/update")
def update_cart_item(
    data: CartUpdateRequest,
    current_user: Optional[User] = Depends(get_current_user_or_none),
    db: Session = Depends(get_db)
):
    item_id = data.item_id
    new_quantity = data.quantity
    query = db.query(CartItem).filter(CartItem.id == item_id)
    if current_user:
        query = query.filter(CartItem.user_id == current_user.id)
    else:
        if not data.session_id:
            raise HTTPException(400, "session_id обязателен для гостя")
        query = query.filter(CartItem.session_id == data.session_id)
    item = query.first()

    if not item:
        raise HTTPException(404, "Элемент не найден")

    item.quantity = max(1, new_quantity)  # минимум 1
    db.commit()
    return {"message": "Количество обновлено"}