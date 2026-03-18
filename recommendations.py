import math
import os
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from ml_dataset import log_ml_interaction
from models import CartItem, Order, OrderItem, Product, RecommendationEvent, User


@dataclass
class RecSettings:
    home_enabled: bool = os.getenv("REC_ENABLE_HOME", "1") == "1"
    product_enabled: bool = os.getenv("REC_ENABLE_PRODUCT", "1") == "1"
    cart_enabled: bool = os.getenv("REC_ENABLE_CART", "1") == "1"
    user_enabled: bool = os.getenv("REC_ENABLE_USER", "1") == "1"
    cache_ttl_seconds: int = int(os.getenv("REC_CACHE_TTL", "120"))


class TTLCache:
    def __init__(self, ttl_seconds: int = 120):
        self.ttl_seconds = ttl_seconds
        self._store: Dict[str, Tuple[float, List[int]]] = {}

    def get(self, key: str) -> Optional[List[int]]:
        item = self._store.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: List[int]) -> None:
        self._store[key] = (time.time() + self.ttl_seconds, value)


def _kbju_vector(product: Product) -> Tuple[float, float, float, float]:
    return (
        float(product.k or 0.0),
        float(product.b or 0.0),
        float(product.j or 0.0),
        float(product.u or 0.0),
    )


def _cosine_similarity(vec1: Tuple[float, float, float, float], vec2: Tuple[float, float, float, float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm1 * norm2)))


def _normalize_popularity(popularity: int) -> float:
    if popularity <= 0:
        return 0.0
    return min(1.0, math.log1p(popularity) / math.log1p(200))


class RecommendationService:
    def __init__(self):
        self.settings = RecSettings()
        self.cache = TTLCache(ttl_seconds=self.settings.cache_ttl_seconds)

    def _load_products_by_ids(self, db: Session, product_ids: List[int]) -> List[Product]:
        if not product_ids:
            return []
        products = db.query(Product).filter(Product.id.in_(product_ids)).all()
        order = {pid: idx for idx, pid in enumerate(product_ids)}
        products.sort(key=lambda p: order.get(p.id, 9999))
        return products

    def get_popular_products(self, db: Session, limit: int = 6) -> List[Product]:
        cache_key = f"popular:{limit}"
        cached_ids = self.cache.get(cache_key)
        if cached_ids is not None:
            return self._load_products_by_ids(db, cached_ids)

        items = (
            db.query(Product)
            .order_by(Product.popularity.desc(), Product.id.asc())
            .limit(limit)
            .all()
        )
        self.cache.set(cache_key, [p.id for p in items])
        return items

    def get_recommend_now(self, db: Session, limit: int = 6) -> List[Product]:
        hour = time.localtime().tm_hour
        cache_key = f"now:{hour}:{limit}"
        cached_ids = self.cache.get(cache_key)
        if cached_ids is not None:
            return self._load_products_by_ids(db, cached_ids)

        categories = [2, 3, 4, 7, 8]
        current_category_id = categories[hour % len(categories)]
        candidates = (
            db.query(Product)
            .filter(Product.category_id == current_category_id)
            .order_by(Product.popularity.desc(), Product.price.asc())
            .limit(limit)
            .all()
        )
        if len(candidates) < limit:
            used_ids = {p.id for p in candidates}
            fallback = (
                db.query(Product)
                .filter(~Product.id.in_(used_ids) if used_ids else True)
                .order_by(Product.popularity.desc(), Product.id.asc())
                .limit(limit - len(candidates))
                .all()
            )
            candidates.extend(fallback)

        self.cache.set(cache_key, [p.id for p in candidates])
        return candidates

    def get_product_recs(self, db: Session, product: Product, limit: int = 6) -> List[Product]:
        if not self.settings.product_enabled:
            return []

        cache_key = f"product:{product.id}:{limit}"
        cached_ids = self.cache.get(cache_key)
        if cached_ids is not None:
            return self._load_products_by_ids(db, cached_ids)

        source_vec = _kbju_vector(product)
        candidates = (
            db.query(Product)
            .filter(Product.id != product.id)
            .all()
        )

        scored = []
        for candidate in candidates:
            same_category = 1.0 if candidate.category_id == product.category_id else 0.0
            kbju_score = _cosine_similarity(_kbju_vector(candidate), source_vec)
            pop_score = _normalize_popularity(candidate.popularity)
            score = 0.50 * same_category + 0.35 * kbju_score + 0.15 * pop_score
            scored.append((score, candidate))

        scored.sort(key=lambda item: item[0], reverse=True)
        result = [candidate for _, candidate in scored[:limit]]
        self.cache.set(cache_key, [p.id for p in result])
        return result

    def get_cart_recs(self, db: Session, cart_items: List[CartItem], limit: int = 6) -> List[Product]:
        if not self.settings.cart_enabled:
            return []

        if not cart_items:
            return self.get_popular_products(db, limit=limit)

        cart_product_ids = {item.product_id for item in cart_items}
        cart_categories: Dict[int, int] = {}
        weighted_total = 0
        kbju_sum = [0.0, 0.0, 0.0, 0.0]

        for item in cart_items:
            qty = max(1, int(item.quantity))
            cart_categories[item.product.category_id] = cart_categories.get(item.product.category_id, 0) + qty
            vec = _kbju_vector(item.product)
            for i in range(4):
                kbju_sum[i] += vec[i] * qty
            weighted_total += qty

        profile_vec = tuple(v / weighted_total for v in kbju_sum) if weighted_total > 0 else (0.0, 0.0, 0.0, 0.0)

        candidates = db.query(Product).filter(~Product.id.in_(cart_product_ids)).all()
        max_cat_weight = max(cart_categories.values()) if cart_categories else 1

        scored = []
        for candidate in candidates:
            cat_weight = cart_categories.get(candidate.category_id, 0) / max_cat_weight
            kbju_score = _cosine_similarity(_kbju_vector(candidate), profile_vec)
            pop_score = _normalize_popularity(candidate.popularity)
            score = 0.45 * cat_weight + 0.35 * kbju_score + 0.20 * pop_score
            scored.append((score, candidate))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _, candidate in scored[:limit]]

    def get_user_recs(
        self,
        db: Session,
        user: Optional[User],
        session_id: Optional[str] = None,
        limit: int = 6,
    ) -> List[Product]:
        recs_with_reasons = self.get_user_recs_with_reasons(
            db=db,
            user=user,
            session_id=session_id,
            limit=limit,
        )
        return [product for product, _ in recs_with_reasons]

    def get_user_recs_with_reasons(
        self,
        db: Session,
        user: Optional[User],
        session_id: Optional[str] = None,
        limit: int = 6,
    ) -> List[Tuple[Product, str]]:
        if not self.settings.user_enabled:
            return []

        if user is None and not session_id:
            return [(p, "Популярный товар") for p in self.get_popular_products(db, limit=limit)]

        now_ts = int(time.time())
        min_ts = now_ts - 90 * 24 * 3600

        order_items_query = (
            db.query(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .filter(Order.created_at >= min_ts)
        )
        if user is not None:
            order_items_query = order_items_query.filter(Order.user_id == user.id)
        else:
            order_items_query = order_items_query.filter(Order.session_id == session_id)

        recent_items = order_items_query.all()
        if not recent_items:
            return [(p, "Популярный товар") for p in self.get_popular_products(db, limit=limit)]

        purchase_stats: Dict[int, Dict[str, object]] = {}
        for item in recent_items:
            product_id = int(item.product_id)
            qty = max(1, int(item.quantity))
            if product_id not in purchase_stats:
                purchase_stats[product_id] = {
                    "qty": 0,
                    "orders": set(),
                }
            purchase_stats[product_id]["qty"] = int(purchase_stats[product_id]["qty"]) + qty
            purchase_stats[product_id]["orders"].add(int(item.order_id))

        seed_product_ids = list(purchase_stats.keys())
        seed_products = db.query(Product).filter(Product.id.in_(seed_product_ids)).all()
        if not seed_products:
            return [(p, "Популярный товар") for p in self.get_popular_products(db, limit=limit)]

        seed_by_id = {p.id: p for p in seed_products}

        seed_scores: Dict[int, float] = {}
        for pid, stat in purchase_stats.items():
            if pid not in seed_by_id:
                continue
            qty_total = float(stat["qty"])
            orders_count = float(len(stat["orders"]))
            seed_scores[pid] = qty_total + orders_count * 1.5

        if not seed_scores:
            return [(p, "Популярный товар") for p in self.get_popular_products(db, limit=limit)]

        sorted_seed_ids = sorted(seed_scores.keys(), key=lambda pid: seed_scores[pid], reverse=True)
        top_seed_ids = sorted_seed_ids[:5]

        max_seed_score = max(seed_scores[pid] for pid in top_seed_ids)
        if max_seed_score <= 0:
            return [(p, "Популярный товар") for p in self.get_popular_products(db, limit=limit)]

        seed_weights = {pid: seed_scores[pid] / max_seed_score for pid in top_seed_ids}

        candidates = db.query(Product).filter(~Product.id.in_(set(seed_product_ids))).all()
        if not candidates:
            return [(p, "Популярный товар") for p in self.get_popular_products(db, limit=limit)]

        scored: List[Tuple[float, Product, str]] = []
        for candidate in candidates:
            candidate_vec = _kbju_vector(candidate)
            similarity_sum = 0.0
            best_seed: Optional[Product] = None
            best_same_category = 0.0
            best_kbju = 0.0
            best_local_score = -1.0

            for seed_id in top_seed_ids:
                seed = seed_by_id.get(seed_id)
                if not seed:
                    continue
                same_category = 1.0 if candidate.category_id == seed.category_id else 0.0
                kbju_score = _cosine_similarity(candidate_vec, _kbju_vector(seed))
                local_similarity = 0.65 * same_category + 0.35 * kbju_score
                similarity_sum += seed_weights[seed_id] * local_similarity

                if local_similarity > best_local_score:
                    best_local_score = local_similarity
                    best_seed = seed
                    best_same_category = same_category
                    best_kbju = kbju_score

            popularity_score = _normalize_popularity(candidate.popularity)
            final_score = 0.85 * similarity_sum + 0.15 * popularity_score
            if best_seed is None:
                reason = "Похожий товар из ваших покупок"
            else:
                category_text = "та же категория" if best_same_category >= 0.5 else "похожая категория"
                reason = f"Похож на {best_seed.name}: {category_text}, близкое КБЖУ ({best_kbju:.2f})"

            scored.append((final_score, candidate, reason))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        result_with_reasons = [(product, reason) for _, product, reason in scored[:limit]]

        if len(result_with_reasons) < limit:
            used_ids = {p.id for p, _ in result_with_reasons}
            fallback = (
                db.query(Product)
                .filter(~Product.id.in_(used_ids) if used_ids else True)
                .order_by(Product.popularity.desc(), Product.id.asc())
                .limit(limit - len(result_with_reasons))
                .all()
            )
            result_with_reasons.extend((p, "Популярный товар (fallback)") for p in fallback)

        return result_with_reasons


def log_recommendation_event(
    db: Session,
    placement: str,
    event_type: str,
    product_id: Optional[int],
    user_id: Optional[int],
    session_id: Optional[str],
    source_product_id: Optional[int] = None,
) -> None:
    created_at = int(time.time())
    event = RecommendationEvent(
        placement=placement,
        event_type=event_type,
        product_id=product_id,
        user_id=user_id,
        session_id=session_id,
        source_product_id=source_product_id,
        created_at=created_at,
    )
    db.add(event)
    db.flush()

    if product_id is not None:
        log_ml_interaction(
            db=db,
            product_id=product_id,
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            placement=placement,
            source_product_id=source_product_id,
            created_at=created_at,
        )


def log_recommendation_impressions(
    db: Session,
    placement: str,
    products: Iterable[Product],
    user_id: Optional[int],
    session_id: Optional[str],
    source_product_id: Optional[int] = None,
) -> None:
    for product in products:
        log_recommendation_event(
            db=db,
            placement=placement,
            event_type="impression",
            product_id=product.id,
            user_id=user_id,
            session_id=session_id,
            source_product_id=source_product_id,
        )
    db.commit()
