import uvicorn
import sqlite3
import time
import os
from fastapi import FastAPI, Depends, Request, Query, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from sqlalchemy.exc import OperationalError

from database import engine, Base, get_db, SessionLocal
from ml_dataset import drop_legacy_training_samples_table, ensure_training_interactions_schema
from models import Category, Product, RecommendationEvent
from routers import users, products, cart, orders, recommendations, ml_dataset
from auth import get_current_user_or_none
from schemas import ProductOut
from recommendations import RecommendationService, log_recommendation_impressions


# Включаем русскую локализацию Swagger UI через параметры swagger_ui_parameters
app = FastAPI(title="Магазин доставки",
              docs_url="/docs",
              redoc_url="/redoc",
              openapi_url="/openapi.json",
              swagger_ui_parameters={
                  "docExpansion": "none",
                  "defaultModelsExpandDepth": -1,
                  # Локализация текста подсказок в Swagger UI можно задавать через locale
                  "locale": "ru"
              })

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(users.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(recommendations.router)
app.include_router(ml_dataset.router)

rec_service = RecommendationService()

print("Создаём таблицы в базе...")
if os.getenv("DB_INIT_SCHEMA", "0") == "1":
    try:
        Base.metadata.create_all(bind=engine)
        print("Таблицы созданы")
    except OperationalError as e:
        if "database is locked" in str(e).lower():
            print("Предупреждение: create_all пропущен, база временно занята")
        else:
            raise
else:
    print("Пропускаем create_all (DB_INIT_SCHEMA=0)")

# Убедимся, что в таблице products есть нужные колонки — добавляем их немедленно при импорте
conn_tmp = None
try:
    conn_tmp = sqlite3.connect('store.db', timeout=1)
    cur_tmp = conn_tmp.cursor()
    cur_tmp.execute("PRAGMA table_info(products)")
    cols = [r[1] for r in cur_tmp.fetchall()]
    for col, col_def in [("k", "REAL"), ("b", "REAL"), ("j", "REAL"), ("u", "REAL"), ("popularity", "INTEGER NOT NULL DEFAULT 0")]:
        if col not in cols:
            try:
                cur_tmp.execute(f"ALTER TABLE products ADD COLUMN {col} {col_def}")
                print(f"Добавлена колонка {col} в products (при импорте)")
            except Exception as e:
                print(f"Не удалось добавить колонку {col} при импорте:", e)
    conn_tmp.commit()
except Exception as e:
    print('Ошибка при проверке колонок products при импорте:', e)
finally:
    if conn_tmp:
        conn_tmp.close()


def init_db():
    conn = None
    try:
        conn = sqlite3.connect('store.db', timeout=30)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(products)")
        existing_cols = [row[1] for row in cursor.fetchall()]
        for col, col_def in [("k", "REAL"), ("b", "REAL"), ("j", "REAL"), ("u", "REAL"), ("popularity", "INTEGER NOT NULL DEFAULT 0")]:
            if col not in existing_cols:
                cursor.execute(f"ALTER TABLE products ADD COLUMN {col} {col_def}")

        cursor.execute("SELECT COUNT(*) FROM products")
        count = cursor.fetchone()[0]

        def backfill_popularity_from_cart():
            cursor.execute(
                """
                UPDATE products
                SET popularity = COALESCE((
                    SELECT SUM(quantity)
                    FROM order_items
                    WHERE order_items.product_id = products.id
                ), 0)
                """
            )

        if count > 0:
            backfill_popularity_from_cart()
            conn.commit()
            print("База уже инициализирована, пропускаем init_db")
            return

        print("Инициализация базы данных...")
        categories = [
            ("Сейчас сезон",),
            ("Овощи и фрукты",),
            ("Молоко, яйца и сыр",),
            ("Мясо и рыба",),
            ("Хлеб и выпечка",),
            ("Готовая еда",),
            ("Сладкое и снеки",),
            ("Напитки",),
            ("Бакалея",),
            ("Для детей",),
            ("Красота и здоровье",),
        ]
        cursor.executemany("INSERT OR IGNORE INTO categories (name) VALUES (?)", categories)

        products_data = [
            ("Мандарины отборные", "600 г • Дарим карточку • -12%", 219.0, "https://images.unsplash.com/photo-1611080626919-7cf5a9dbab5b?w=400", "Овощи и фрукты", 20.0, 1.0, 0.5, 120.0, 12),
            ("Апельсины", "1 кг • Дарим карточку • -25%", 149.0, "https://images.unsplash.com/photo-1502741126161-b048400d27b8?w=400", "Овощи и фрукты", 11.0, 0.9, 0.2, 47.0, 11),
            ("Белый виноград Shine Muscat", "500 г • -10%", 449.0, "https://images.unsplash.com/photo-1567306226416-28f0efdc88ce?w=400", "Овощи и фрукты", 18.0, 0.6, 0.4, 90.0, 7),
            ("Груши Пакхам", "500 г • -15%", 175.0, "https://images.unsplash.com/photo-1574226516831-e1dff420e3f7?w=400", "Овощи и фрукты", 16.0, 0.5, 0.3, 80.0, 6),
            ("Киви Артфрут Gold", "3 шт • Дарим карточку • -14%", 170.0, "https://images.unsplash.com/photo-1574226516831-e1dff420e3f7?w=400", "Овощи и фрукты", 14.0, 1.2, 0.6, 70.0, 8),
            ("Молоко Самокат 3.2%", "1 л", 89.0, "https://images.unsplash.com/photo-1582719478149-59d4b7f0f5d3?w=400", "Молоко, яйца и сыр", 5.0, 3.2, 3.2, 60.0, 14),
            ("Сыр твердый", "200 г", 320.0, "https://images.unsplash.com/photo-1544025162-d76694265947?w=400", "Молоко, яйца и сыр", 1.0, 25.0, 33.0, 400.0, 9),
            ("Куриное филе", "500 г", 299.0, "https://images.unsplash.com/photo-1604908177522-4d9aef0d5c7a?w=400", "Мясо и рыба", 0.0, 31.0, 3.6, 165.0, 13),
            ("Шоколад молочный", "100 г • -20%", 89.0, "https://images.unsplash.com/photo-1549880338-65ddcdfd017b?w=400", "Сладкое и снеки", 56.0, 7.0, 31.0, 540.0, 10),
        ]

        for name, desc, price, img, cat_name, k_val, b_val, j_val, u_val, popularity in products_data:
            cursor.execute("SELECT id FROM categories WHERE name = ?", (cat_name,))
            row = cursor.fetchone()
            if row:
                cat_id = row[0]
            else:
                cursor.execute("INSERT INTO categories (name) VALUES (?)", (cat_name,))
                cat_id = cursor.lastrowid

            cursor.execute(
                "UPDATE products SET description = ?, price = ?, image_url = ?, category_id = ?, k = ?, b = ?, j = ?, u = ?, popularity = COALESCE(popularity, ?) WHERE name = ?",
                (desc, price, img, cat_id, k_val, b_val, j_val, u_val, popularity, name),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO products (name, description, price, image_url, category_id, k, b, j, u, popularity) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, desc, price, img, cat_id, k_val, b_val, j_val, u_val, popularity),
                )

        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


@app.on_event("startup")
async def startup_event():
    try:
        init_db()
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e).lower():
            print("Предупреждение: init_db пропущен, база временно занята")
        else:
            raise

    db = SessionLocal()
    try:
        dropped_legacy = drop_legacy_training_samples_table(db)
        if dropped_legacy:
            print("Удалена legacy-таблица recommendation_training_samples")
        ensure_training_interactions_schema(db)
    finally:
        db.close()


@app.get("/")
async def index(
    request: Request,
    category_id: int | None = Query(None),
    search: str | None = Query(None),
    session_id: str | None = Query(None),
    feed: str | None = Query(None),
    current_user=Depends(get_current_user_or_none),
    db: Session = Depends(get_db),
):
    categories = []
    products = []
    selected_feed = feed if feed in {"popular", "recommended"} else None
    if selected_feed == "recommended" and not current_user:
        selected_feed = None

    for attempt in range(3):
        try:
            categories = db.query(Category).all()
            query = db.query(Product)

            if selected_feed == "popular":
                products = rec_service.get_popular_products(db, limit=24)
            elif selected_feed == "recommended":
                products = rec_service.get_user_recs(db, user=current_user, session_id=session_id, limit=24)
            else:
                if category_id:
                    query = query.filter(Product.category_id == category_id)
                if search:
                    tokens = [t.strip().casefold() for t in search.split() if t.strip()]
                    candidates = query.all()
                    results = []
                    for p in candidates:
                        name = (p.name or "").casefold()
                        desc = (p.description or "").casefold()
                        ok = True
                        for t in tokens:
                            if t not in name and t not in desc:
                                ok = False
                                break
                        if ok:
                            results.append(p)
                    products = results
                else:
                    products = query.all()
            break
        except OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < 2:
                time.sleep(0.2)
                continue
            categories = []
            products = []
            break

    if selected_feed == "popular" and products:
        log_recommendation_impressions(
            db=db,
            placement="home_popular",
            products=products,
            user_id=current_user.id if current_user else None,
            session_id=session_id,
        )
    if selected_feed == "recommended" and products:
        log_recommendation_impressions(
            db=db,
            placement="home_recommended",
            products=products,
            user_id=current_user.id if current_user else None,
            session_id=session_id,
        )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "categories": categories,
            "products": products,
            "current_user": current_user,
            "search_query": search or "",
            "selected_category_id": category_id,  # ← добавили это
            "selected_feed": selected_feed,
        },
    )


@app.get("/products/{product_id}")
async def product_detail(
    request: Request,
    product_id: int,
    session_id: str | None = Query(None),
    current_user=Depends(get_current_user_or_none),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    categories = db.query(Category).all()

    also_buy = rec_service.get_product_recs(db, product=product, limit=6)
    if also_buy:
        log_recommendation_impressions(
            db=db,
            placement="product_also_buy",
            products=also_buy,
            user_id=current_user.id if current_user else None,
            session_id=session_id,
            source_product_id=product.id,
        )

    return templates.TemplateResponse(
        "product.html",
        {
            "request": request,
            "product": product,
            "current_user": current_user,
            "also_buy": also_buy,
            "categories": categories,
        },
    )


@app.get("/cart")
async def cart_page(
    request: Request,
    session_id: str | None = Query(None),
    current_user=Depends(get_current_user_or_none),
    db: Session = Depends(get_db),
):
    from routers.cart import get_cart  # late import to avoid circular

    if current_user or session_id:
        cart_items = get_cart(current_user=current_user, session_id=session_id, db=db)
    else:
        cart_items = []
    total_price = sum(item.product.price * item.quantity for item in cart_items)
    complete_order_recs = rec_service.get_cart_recs(db, cart_items=cart_items, limit=6)
    if complete_order_recs:
        log_recommendation_impressions(
            db=db,
            placement="cart_complete_order",
            products=complete_order_recs,
            user_id=current_user.id if current_user else None,
            session_id=session_id,
        )

    return templates.TemplateResponse(
        "cart.html",
        {
            "request": request,
            "cart_items": cart_items,
            "total_price": total_price,
            "current_user": current_user,
            "complete_order_recs": complete_order_recs,
        },
    )


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/api/products/{product_id}", response_model=ProductOut)
def api_get_product(product_id: int, db: Session = Depends(get_db)):
    print(f"API GET /api/products/{product_id}")
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return product

# Совместимый JSON-эндпоинт по старому пути
@app.get("/products/{product_id}/json", response_model=ProductOut)
def product_json(product_id: int, db: Session = Depends(get_db)):
    print(f"API GET /products/{product_id}/json")
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return product


@app.get("/api/recommendations/metrics")
def recommendations_metrics(hours: int = Query(24, ge=1, le=168), db: Session = Depends(get_db)):
    since_ts = int(time.time()) - hours * 3600
    events = db.query(RecommendationEvent).filter(RecommendationEvent.created_at >= since_ts).all()

    summary = {}
    for event in events:
        key = f"{event.placement}:{event.event_type}"
        summary[key] = summary.get(key, 0) + 1

    return {
        "hours": hours,
        "events_total": len(events),
        "by_placement_event": summary,
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)