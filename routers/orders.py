import time
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from auth import get_current_user_or_none
from database import get_db
from ml_dataset import sync_order_with_training_interactions
from models import CartItem, Order, OrderItem, Product, User
from schemas import OrderCreate, OrderOut

router = APIRouter(prefix="/api/orders", tags=["Заказы"])


def ensure_orders_schema(db: Session):
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price REAL NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
            """
        )
    )
    rows = db.execute(text("PRAGMA table_info(orders)")).all()
    cols = [r[1] for r in rows]
    if "items_json" not in cols:
        db.execute(text("ALTER TABLE orders ADD COLUMN items_json TEXT"))
    db.commit()


def _resolve_order_context(
    current_user: Optional[User],
    session_id: Optional[str],
    delivery_address: Optional[str],
):
    if current_user:
        address = delivery_address or current_user.delivery_address
        if not address:
            raise HTTPException(status_code=400, detail="Укажите адрес доставки")
        return current_user.id, None, address

    if not session_id:
        raise HTTPException(status_code=400, detail="Для гостя нужен session_id")
    if not delivery_address:
        raise HTTPException(status_code=400, detail="Для гостя нужен адрес доставки")
    return None, session_id, delivery_address


@router.post("/", response_model=OrderOut)
def create_order_from_cart(
    payload: OrderCreate,
    current_user: Optional[User] = Depends(get_current_user_or_none),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    ensure_orders_schema(db)

    user_id, guest_session_id, address = _resolve_order_context(
        current_user=current_user,
        session_id=session_id,
        delivery_address=payload.delivery_address,
    )

    cart_query = db.query(CartItem)
    if user_id is not None:
        cart_items = cart_query.filter(CartItem.user_id == user_id).all()
    else:
        cart_items = cart_query.filter(CartItem.session_id == guest_session_id).all()

    if not cart_items:
        raise HTTPException(status_code=400, detail="Корзина пуста")

    ts = int(time.time())
    total = sum(item.product.price * item.quantity for item in cart_items)
    items_snapshot = [
        {
            "product_id": item.product_id,
            "name": item.product.name if item.product else None,
            "quantity": max(1, int(item.quantity)),
            "unit_price": float(item.product.price) if item.product else 0.0,
            "line_total": (float(item.product.price) if item.product else 0.0) * max(1, int(item.quantity)),
        }
        for item in cart_items
    ]
    order = Order(
        user_id=user_id,
        session_id=guest_session_id,
        status=payload.status or "created",
        total=total,
        delivery_address=address,
        items_json=json.dumps(items_snapshot, ensure_ascii=False),
        created_at=ts,
    )
    db.add(order)
    db.flush()

    created_order_items = []
    for cart_item in cart_items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=cart_item.product_id,
            quantity=max(1, int(cart_item.quantity)),
            unit_price=float(cart_item.product.price),
            created_at=ts,
        )
        db.add(order_item)
        created_order_items.append(order_item)
        db.delete(cart_item)

    if current_user and payload.delivery_address and current_user.delivery_address != payload.delivery_address:
        current_user.delivery_address = payload.delivery_address

    sync_order_with_training_interactions(db=db, order=order, order_items=created_order_items)

    db.commit()
    db.refresh(order)
    return order


@router.get("/", response_model=List[OrderOut])
def list_orders(
    current_user: Optional[User] = Depends(get_current_user_or_none),
    session_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    ensure_orders_schema(db)

    query = db.query(Order)
    if current_user:
        query = query.filter(Order.user_id == current_user.id)
    else:
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id обязателен для гостя")
        query = query.filter(Order.session_id == session_id)

    return query.order_by(Order.created_at.desc()).limit(limit).all()
