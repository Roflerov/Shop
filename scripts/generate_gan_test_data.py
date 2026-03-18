import argparse
import json
import random
import sqlite3
import time
import uuid
from collections import defaultdict

import numpy as np
import pandas as pd

try:
    from ctgan import CTGAN
except Exception as exc:
    raise SystemExit(
        "Не удалось импортировать ctgan. Установите зависимости: pip install -r requirements.txt"
    ) from exc


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

ALLOWED_PLACEMENTS = {
    "main",
    "cart",
    "product_card",
    "search",
    "recommendation_block",
    "checkout",
}

GAN_PROMPT_TEMPLATE = """
Сгенерируй синтетические записи взаимодействий для ecommerce.
Ограничения:
1) Используй только product_id, существующие в таблице products.
2) event_type только из: view, add_to_cart, purchase, click_recommendation, remove_from_cart.
3) implicit_weight должен соответствовать маппингу: view=1, click_recommendation=2, add_to_cart=3, purchase=10, remove_from_cart=-1.
4) user_id может быть NULL только если заполнен session_id.
5) placement только из: main, cart, product_card, search, recommendation_block, checkout.
6) Для заказов каждый order_id должен содержать минимум 2 разных product_id.
7) category_id и product_popularity должны соответствовать данным products.
""".strip()


def normalize_event_type(event_type: str) -> str:
    event = (event_type or "").strip().lower()
    return EVENT_ALIAS.get(event, event)


def weighted_choice(products: list[dict], rng: random.Random) -> dict:
    if not products:
        raise ValueError("Список продуктов пуст")
    weights = [max(1, int(product["popularity"] or 0)) for product in products]
    return rng.choices(products, weights=weights, k=1)[0]


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ml_training_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_id TEXT,
            product_id INTEGER NOT NULL,
            category_id INTEGER,
            product_popularity INTEGER DEFAULT 0,
            event_type TEXT NOT NULL,
            implicit_weight REAL NOT NULL,
            placement TEXT,
            source_product_id INTEGER,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id),
            CHECK (user_id IS NOT NULL OR session_id IS NOT NULL)
        )
        """
    )


def fetch_products(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, category_id, COALESCE(popularity, 0), COALESCE(price, 0)
        FROM products
        ORDER BY id
        """
    ).fetchall()
    products = [
        {
            "id": int(row[0]),
            "category_id": int(row[1]) if row[1] is not None else None,
            "popularity": int(row[2] or 0),
            "price": float(row[3] or 0.0),
        }
        for row in rows
    ]
    if not products:
        raise RuntimeError("В таблице products нет данных. Сначала заполните каталог.")
    return products


def fetch_users(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute("SELECT id FROM users ORDER BY id").fetchall()
    return [int(row[0]) for row in rows]


def fetch_session_pool(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT session_id
        FROM ml_training_interactions
        WHERE session_id IS NOT NULL AND session_id != ''
        """
    ).fetchall()
    return [str(row[0]) for row in rows if row[0]]


def build_interaction_training_df(conn: sqlite3.Connection) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT
            event_type,
            COALESCE(placement, 'main') AS placement,
            category_id,
            product_popularity,
            source_product_id,
            user_id,
            session_id,
            created_at
        FROM ml_training_interactions
        """
    ).fetchall()

    records = []
    for row in rows:
        event_type = normalize_event_type(row[0])
        if event_type not in EVENT_WEIGHTS:
            continue
        placement = str(row[1] or "main")
        if placement not in ALLOWED_PLACEMENTS:
            placement = "main"
        ts = int(row[7] or int(time.time()))
        dt = time.localtime(ts)
        records.append(
            {
                "event_type": event_type,
                "placement": placement,
                "category_id": int(row[2]) if row[2] is not None else -1,
                "product_popularity": int(row[3] or 0),
                "has_source": 1 if row[4] is not None else 0,
                "actor_type": "user" if row[5] is not None else "session",
                "hour": int(dt.tm_hour),
                "dow": int(dt.tm_wday),
            }
        )

    if not records:
        legacy_events = conn.execute(
            """
            SELECT
                event_type,
                COALESCE(placement, 'main') AS placement,
                user_id,
                session_id,
                product_id,
                source_product_id,
                created_at
            FROM recommendation_events
            """
        ).fetchall()

        products = {row[0]: (row[1], row[2]) for row in conn.execute("SELECT id, category_id, COALESCE(popularity, 0) FROM products")}
        for event in legacy_events:
            event_type = normalize_event_type(event[0])
            if event_type not in EVENT_WEIGHTS:
                continue
            product_id = int(event[4]) if event[4] is not None else None
            if product_id is None or product_id not in products:
                continue
            category_id, popularity = products[product_id]
            placement = str(event[1] or "main")
            if placement not in ALLOWED_PLACEMENTS:
                placement = "main"
            ts = int(event[6] or int(time.time()))
            dt = time.localtime(ts)
            records.append(
                {
                    "event_type": event_type,
                    "placement": placement,
                    "category_id": int(category_id) if category_id is not None else -1,
                    "product_popularity": int(popularity or 0),
                    "has_source": 1 if event[5] is not None else 0,
                    "actor_type": "user" if event[2] is not None else "session",
                    "hour": int(dt.tm_hour),
                    "dow": int(dt.tm_wday),
                }
            )

    if not records:
        raise RuntimeError("Недостаточно исходных событий для обучения GAN.")

    return pd.DataFrame(records)


def train_ctgan(df: pd.DataFrame, discrete_columns: list[str], epochs: int, seed: int) -> CTGAN:
    model = CTGAN(epochs=epochs, verbose=False)
    model.set_random_state(seed)
    model.fit(df, discrete_columns=discrete_columns)
    return model


def sample_timestamp(hour: int, rng: random.Random) -> int:
    now = int(time.time())
    days_back = rng.randint(0, 60)
    ts = now - days_back * 24 * 3600
    dt = time.localtime(ts)
    return int(
        time.mktime(
            (
                dt.tm_year,
                dt.tm_mon,
                dt.tm_mday,
                max(0, min(23, int(hour))),
                rng.randint(0, 59),
                rng.randint(0, 59),
                dt.tm_wday,
                dt.tm_yday,
                dt.tm_isdst,
            )
        )
    )


def insert_interaction_row(
    conn: sqlite3.Connection,
    *,
    user_id: int | None,
    session_id: str | None,
    product_id: int,
    category_id: int | None,
    product_popularity: int,
    event_type: str,
    placement: str,
    source_product_id: int | None,
    created_at: int,
) -> None:
    conn.execute(
        """
        INSERT INTO ml_training_interactions
        (user_id, session_id, product_id, category_id, product_popularity, event_type, implicit_weight, placement, source_product_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            session_id,
            product_id,
            category_id,
            product_popularity,
            event_type,
            float(EVENT_WEIGHTS[event_type]),
            placement,
            source_product_id,
            created_at,
        ),
    )


def generate_ml_interactions(
    conn: sqlite3.Connection,
    products: list[dict],
    users: list[int],
    sessions: list[str],
    target_count: int,
    epochs: int,
    seed: int,
) -> int:
    rng = random.Random(seed)
    np.random.seed(seed)

    by_category = defaultdict(list)
    for product in products:
        by_category[product["category_id"]].append(product)

    train_df = build_interaction_training_df(conn)
    if len(train_df) < 50:
        bootstrap = train_df.sample(n=min(200, len(train_df)), replace=True, random_state=seed)
        train_df = pd.concat([train_df, bootstrap], ignore_index=True)

    discrete = ["event_type", "placement", "category_id", "has_source", "actor_type", "hour", "dow"]
    gan = train_ctgan(train_df, discrete_columns=discrete, epochs=epochs, seed=seed)
    sampled = gan.sample(target_count)

    inserted = 0
    for _, row in sampled.iterrows():
        event_type = normalize_event_type(str(row.get("event_type", "view")))
        if event_type not in EVENT_WEIGHTS:
            event_type = "view"

        placement = str(row.get("placement", "main"))
        if placement not in ALLOWED_PLACEMENTS:
            placement = "main"

        category_id_raw = row.get("category_id", -1)
        category_id = int(category_id_raw) if pd.notna(category_id_raw) else -1

        category_products = by_category.get(category_id) or products
        product = weighted_choice(category_products, rng)

        source_product_id = None
        has_source = int(round(float(row.get("has_source", 0)))) if pd.notna(row.get("has_source", 0)) else 0
        if has_source == 1 and len(category_products) > 1:
            source_product = weighted_choice(category_products, rng)
            if source_product["id"] != product["id"]:
                source_product_id = int(source_product["id"])

        actor_type = str(row.get("actor_type", "session"))
        user_id = None
        session_id = None
        if actor_type == "user" and users:
            user_id = int(rng.choice(users))
        else:
            session_id = rng.choice(sessions)

        hour_value = row.get("hour", rng.randint(0, 23))
        hour = int(max(0, min(23, int(round(float(hour_value))))))
        created_at = sample_timestamp(hour=hour, rng=rng)

        insert_interaction_row(
            conn,
            user_id=user_id,
            session_id=session_id,
            product_id=int(product["id"]),
            category_id=product["category_id"],
            product_popularity=int(product["popularity"]),
            event_type=event_type,
            placement=placement,
            source_product_id=source_product_id,
            created_at=created_at,
        )
        inserted += 1

    return inserted


def build_order_profile_df(conn: sqlite3.Connection) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT
            COALESCE(o.status, 'created') AS status,
            CASE WHEN o.user_id IS NULL THEN 'session' ELSE 'user' END AS actor_type,
            COUNT(oi.id) AS items_count,
            AVG(oi.quantity) AS avg_quantity
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        GROUP BY o.id
        """
    ).fetchall()

    if not rows:
        return pd.DataFrame(
            [
                {"status": "created", "actor_type": "session", "items_count": 3, "avg_quantity": 1.6},
                {"status": "created", "actor_type": "user", "items_count": 4, "avg_quantity": 1.8},
                {"status": "created", "actor_type": "session", "items_count": 2, "avg_quantity": 1.4},
            ]
        )

    data = []
    for row in rows:
        data.append(
            {
                "status": str(row[0] or "created"),
                "actor_type": str(row[1] or "session"),
                "items_count": max(2, int(row[2] or 2)),
                "avg_quantity": float(row[3] or 1.5),
            }
        )
    return pd.DataFrame(data)


def generate_orders_with_multiple_items(
    conn: sqlite3.Connection,
    products: list[dict],
    users: list[int],
    sessions: list[str],
    target_orders: int,
    epochs: int,
    seed: int,
) -> tuple[int, int]:
    rng = random.Random(seed + 99)
    np.random.seed(seed + 99)

    profile_df = build_order_profile_df(conn)
    if len(profile_df) < 30:
        profile_df = pd.concat([profile_df, profile_df.sample(n=60, replace=True, random_state=seed)], ignore_index=True)

    gan = train_ctgan(profile_df, discrete_columns=["status", "actor_type", "items_count"], epochs=epochs, seed=seed + 99)
    sampled = gan.sample(target_orders)

    order_inserted = 0
    items_inserted = 0
    all_products = products[:]

    for _, profile in sampled.iterrows():
        items_count_raw = profile.get("items_count", 3)
        items_count = max(2, min(8, int(round(float(items_count_raw)))))

        actor_type = str(profile.get("actor_type", "session"))
        status = str(profile.get("status", "created")) or "created"
        avg_qty = max(1.0, float(profile.get("avg_quantity", 1.6)))

        user_id = None
        session_id = None
        if actor_type == "user" and users:
            user_id = int(rng.choice(users))
        else:
            session_id = rng.choice(sessions)

        created_at = sample_timestamp(hour=rng.randint(8, 23), rng=rng)

        if items_count <= len(all_products):
            selected_products = rng.sample(all_products, k=items_count)
        else:
            selected_products = [weighted_choice(all_products, rng) for _ in range(items_count)]

        unique_products = []
        seen = set()
        for product in selected_products:
            if product["id"] not in seen:
                unique_products.append(product)
                seen.add(product["id"])
        while len(unique_products) < 2:
            candidate = weighted_choice(all_products, rng)
            if candidate["id"] not in seen:
                unique_products.append(candidate)
                seen.add(candidate["id"])

        total = 0.0
        items_payload = []
        line_items = []

        for product in unique_products:
            quantity = max(1, int(round(rng.gauss(avg_qty, 0.8))))
            unit_price = float(product["price"])
            line_total = unit_price * quantity
            total += line_total
            items_payload.append(
                {
                    "product_id": int(product["id"]),
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": line_total,
                }
            )
            line_items.append((int(product["id"]), quantity, unit_price))

        cursor = conn.execute(
            """
            INSERT INTO orders (user_id, session_id, status, total, delivery_address, items_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                session_id,
                status,
                round(total, 2),
                "Синтетический адрес (GAN)",
                json.dumps(items_payload, ensure_ascii=False),
                created_at,
            ),
        )
        order_id = int(cursor.lastrowid)
        order_inserted += 1

        for product_id, quantity, unit_price in line_items:
            conn.execute(
                """
                INSERT INTO order_items (order_id, product_id, quantity, unit_price, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, product_id, quantity, unit_price, created_at),
            )
            items_inserted += 1

            product = next(product for product in all_products if product["id"] == product_id)
            insert_interaction_row(
                conn,
                user_id=user_id,
                session_id=session_id,
                product_id=product_id,
                category_id=product["category_id"],
                product_popularity=int(product["popularity"]),
                event_type="purchase",
                placement="checkout",
                source_product_id=None,
                created_at=created_at,
            )

    return order_inserted, items_inserted


def build_sessions(base_sessions: list[str], target_size: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    sessions = base_sessions[:]
    while len(sessions) < target_size:
        sessions.append(str(uuid.uuid4()))
    rng.shuffle(sessions)
    return sessions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Генерация синтетических данных через GAN для ml_training_interactions и заказов")
    parser.add_argument("--db", default="store.db", help="Путь к SQLite базе")
    parser.add_argument("--interactions", type=int, default=1500, help="Сколько взаимодействий сгенерировать")
    parser.add_argument("--orders", type=int, default=300, help="Сколько заказов сгенерировать")
    parser.add_argument("--epochs", type=int, default=100, help="Эпохи CTGAN")
    parser.add_argument("--seed", type=int, default=42, help="Seed для воспроизводимости")
    parser.add_argument("--show-prompt", action="store_true", help="Показать промпт для генерации")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.show_prompt:
        print("--- GAN PROMPT ---")
        print(GAN_PROMPT_TEMPLATE)
        print("------------------")

    conn = sqlite3.connect(args.db, timeout=30)
    try:
        ensure_schema(conn)

        products = fetch_products(conn)
        users = fetch_users(conn)
        session_pool = build_sessions(fetch_session_pool(conn), target_size=300, seed=args.seed)

        inserted_interactions = generate_ml_interactions(
            conn=conn,
            products=products,
            users=users,
            sessions=session_pool,
            target_count=max(0, int(args.interactions)),
            epochs=max(1, int(args.epochs)),
            seed=args.seed,
        )

        inserted_orders, inserted_order_items = generate_orders_with_multiple_items(
            conn=conn,
            products=products,
            users=users,
            sessions=session_pool,
            target_orders=max(0, int(args.orders)),
            epochs=max(1, int(args.epochs)),
            seed=args.seed,
        )

        # Пересчитываем popularity на основе order_items
        conn.execute(
            """
            UPDATE products
            SET popularity = COALESCE((
                SELECT SUM(quantity)
                FROM order_items
                WHERE order_items.product_id = products.id
            ), 0)
            """
        )
        conn.commit()

        # Обновляем product_popularity в ml_training_interactions по актуальным значениям
        conn.execute(
            """
            UPDATE ml_training_interactions
            SET product_popularity = (
                SELECT COALESCE(popularity, 0) FROM products
                WHERE products.id = ml_training_interactions.product_id
            )
            """
        )
        conn.commit()

        print("GAN-генерация завершена")
        print(f"- interactions inserted: {inserted_interactions}")
        print(f"- orders inserted: {inserted_orders}")
        print(f"- order_items inserted: {inserted_order_items}")
        print("- constraint: в каждом заказе >= 2 разных товаров")
        print("- constraint: используются только существующие product_id")
        print("- popularity: пересчитана в products и ml_training_interactions")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
