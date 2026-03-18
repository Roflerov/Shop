import time
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from models import MLTrainingInteraction, Order, OrderItem, Product, RecommendationEvent


EVENT_WEIGHTS = {
    "view": 1.0,
    "add_to_cart": 3.0,
    "purchase": 10.0,
    "click_recommendation": 2.0,
    "remove_from_cart": -1.0,
}

EVENT_ALIAS = {
    "impression": "view",
}


def normalize_event_type(event_type: str) -> str:
    normalized = (event_type or "").strip().lower()
    return EVENT_ALIAS.get(normalized, normalized)


def ensure_training_interactions_schema(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ml_training_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NULL,
                session_id TEXT NULL,
                product_id INTEGER NOT NULL,
                category_id INTEGER NULL,
                product_popularity INTEGER NOT NULL DEFAULT 0,
                event_type TEXT NOT NULL CHECK (event_type IN ('view', 'add_to_cart', 'purchase', 'click_recommendation', 'remove_from_cart')),
                implicit_weight REAL NOT NULL,
                placement TEXT NULL,
                source_product_id INTEGER NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id),
                CHECK (user_id IS NOT NULL OR session_id IS NOT NULL)
            )
            """
        )
    )
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_ml_inter_user_time ON ml_training_interactions (user_id, created_at)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_ml_inter_session_time ON ml_training_interactions (session_id, created_at)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_ml_inter_product_time ON ml_training_interactions (product_id, created_at)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_ml_inter_event_time ON ml_training_interactions (event_type, created_at)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_ml_inter_placement_time ON ml_training_interactions (placement, created_at)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_ml_inter_source ON ml_training_interactions (source_product_id)"))
    db.commit()


def drop_legacy_training_samples_table(db: Session) -> bool:
    table_exists = db.execute(
        text(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'recommendation_training_samples'
            LIMIT 1
            """
        )
    ).scalar()

    if not table_exists:
        return False

    db.execute(text("DROP TABLE IF EXISTS recommendation_training_samples"))
    db.commit()
    return True


def _interaction_exists(
    db: Session,
    user_id: Optional[int],
    session_id: Optional[str],
    product_id: int,
    event_type: str,
    placement: Optional[str],
    source_product_id: Optional[int],
    created_at: int,
) -> bool:
    query = db.query(MLTrainingInteraction).filter(
        MLTrainingInteraction.product_id == product_id,
        MLTrainingInteraction.event_type == event_type,
        MLTrainingInteraction.created_at == created_at,
    )
    if user_id is not None:
        query = query.filter(MLTrainingInteraction.user_id == user_id)
    else:
        query = query.filter(MLTrainingInteraction.user_id.is_(None))

    if session_id:
        query = query.filter(MLTrainingInteraction.session_id == session_id)
    else:
        query = query.filter(MLTrainingInteraction.session_id.is_(None))

    if placement:
        query = query.filter(MLTrainingInteraction.placement == placement)
    else:
        query = query.filter(MLTrainingInteraction.placement.is_(None))

    if source_product_id is not None:
        query = query.filter(MLTrainingInteraction.source_product_id == source_product_id)
    else:
        query = query.filter(MLTrainingInteraction.source_product_id.is_(None))

    return query.first() is not None


def log_ml_interaction(
    db: Session,
    product_id: int,
    event_type: str,
    user_id: Optional[int],
    session_id: Optional[str],
    placement: Optional[str] = None,
    source_product_id: Optional[int] = None,
    created_at: Optional[int] = None,
) -> Optional[MLTrainingInteraction]:
    normalized_event_type = normalize_event_type(event_type)
    if normalized_event_type not in EVENT_WEIGHTS:
        return None

    if user_id is None and not session_id:
        return None

    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        return None

    ts = created_at or int(time.time())
    if _interaction_exists(
        db=db,
        user_id=user_id,
        session_id=session_id,
        product_id=product_id,
        event_type=normalized_event_type,
        placement=placement,
        source_product_id=source_product_id,
        created_at=ts,
    ):
        return None

    row = MLTrainingInteraction(
        user_id=user_id,
        session_id=session_id,
        product_id=product.id,
        category_id=product.category_id,
        product_popularity=int(product.popularity or 0),
        event_type=normalized_event_type,
        implicit_weight=EVENT_WEIGHTS[normalized_event_type],
        placement=placement,
        source_product_id=source_product_id,
        created_at=ts,
    )
    db.add(row)
    db.flush()
    return row


def log_ml_impressions(
    db: Session,
    products: Iterable[Product],
    user_id: Optional[int],
    session_id: Optional[str],
    placement: Optional[str],
    source_product_id: Optional[int] = None,
) -> int:
    added = 0
    ts = int(time.time())
    for product in products:
        row = log_ml_interaction(
            db=db,
            product_id=int(product.id),
            event_type="view",
            user_id=user_id,
            session_id=session_id,
            placement=placement,
            source_product_id=source_product_id,
            created_at=ts,
        )
        if row is not None:
            added += 1
    return added


def sync_order_with_training_interactions(
    db: Session,
    order: Order,
    order_items: Iterable[OrderItem],
) -> int:
    added = 0
    for item in order_items:
        row = log_ml_interaction(
            db=db,
            product_id=int(item.product_id),
            event_type="purchase",
            user_id=order.user_id,
            session_id=order.session_id,
            placement="checkout",
            created_at=int(order.created_at),
        )
        if row is not None:
            added += 1
    return added


def backfill_ml_interactions(db: Session) -> dict[str, int]:
    ensure_training_interactions_schema(db)

    stats = {
        "events_added": 0,
        "purchases_added": 0,
    }

    recommendation_events = (
        db.query(RecommendationEvent)
        .order_by(RecommendationEvent.created_at.asc(), RecommendationEvent.id.asc())
        .all()
    )
    for event in recommendation_events:
        if event.product_id is None:
            continue
        row = log_ml_interaction(
            db=db,
            product_id=int(event.product_id),
            event_type=event.event_type,
            user_id=event.user_id,
            session_id=event.session_id,
            placement=event.placement,
            source_product_id=event.source_product_id,
            created_at=int(event.created_at),
        )
        if row is not None:
            stats["events_added"] += 1

    order_rows = (
        db.query(OrderItem, Order)
        .join(Order, Order.id == OrderItem.order_id)
        .order_by(Order.created_at.asc(), OrderItem.id.asc())
        .all()
    )
    for order_item, order in order_rows:
        row = log_ml_interaction(
            db=db,
            product_id=int(order_item.product_id),
            event_type="purchase",
            user_id=order.user_id,
            session_id=order.session_id,
            placement="checkout",
            created_at=int(order.created_at),
        )
        if row is not None:
            stats["purchases_added"] += 1

    db.commit()
    return stats