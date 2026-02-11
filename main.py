import uvicorn
import sqlite3
from fastapi import FastAPI, Depends, Request, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from database import engine, Base, get_db
from models import Category, Product
from routers import users, products, cart
from auth import get_current_user_or_none
from schemas import ProductOut


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

print("Создаём таблицы в базе...")
Base.metadata.create_all(bind=engine)
print("Таблицы созданы")

# Убедимся, что в таблице products есть колонки для КБЖУ — добавляем их немедленно при импорте
try:
    conn_tmp = sqlite3.connect('store.db', timeout=10)
    cur_tmp = conn_tmp.cursor()
    cur_tmp.execute("PRAGMA table_info(products)")
    cols = [r[1] for r in cur_tmp.fetchall()]
    for col, col_def in [("k", "REAL"), ("b", "REAL"), ("j", "REAL"), ("u", "REAL")]:
        if col not in cols:
            try:
                cur_tmp.execute(f"ALTER TABLE products ADD COLUMN {col} {col_def}")
                print(f"Добавлена колонка {col} в products (при импорте)")
            except Exception as e:
                print(f"Не удалось добавить колонку {col} при импорте:", e)
    conn_tmp.commit()
    conn_tmp.close()
except Exception as e:
    print('Ошибка при проверке колонок products при импорте:', e)


def init_db():
    # добавляем timeout, чтобы при кратковременной занятости БД другой сессией было попытки ожидания
    conn = sqlite3.connect('store.db', timeout=10)
    cursor = conn.cursor()

    # Проверяем, есть ли уже товары
    cursor.execute("SELECT COUNT(*) FROM products")
    count = cursor.fetchone()[0]

    # Проверка и добавление колонок для КБЖУ, если их нет
    cursor.execute("PRAGMA table_info(products)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    for col, col_def in [("k", "REAL"), ("b", "REAL"), ("j", "REAL"), ("u", "REAL")]:
        if col not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE products ADD COLUMN {col} {col_def}")
                print(f"Добавлена колонка {col} в products")
            except Exception as e:
                print(f"Не удалось добавить колонку {col}:", e)

    if count > 0:
        print("База уже инициализирована, пропускаем init_db")
        # Но всё равно согласуем category_id существующих товаров на случай, если были некорректные id
        # (например, после правок в products_data)
        # Сопоставление name->cat_name берём из products_data ниже; поэтому вызываем reconcile
        def reconcile_existing_products():
            # более гибкое сопоставление: подстроки -> имя категории
            substr_to_cat = {
                "Мандари": "Овощи и фрукты",
                "Апельс": "Овощи и фрукты",
                "виноград": "Овощи и фрукты",
                "Груши": "Овощи и фрукты",
                "Киви": "Овощи и фрукты",
                "Молоко": "Молоко, яйца и сыр",
                "Сыр": "Молоко, яйца и сыр",
                "Кури": "Мясо и рыба",
                "Шоколад": "Сладкое и снеки",
            }
            for substr, cat_name in substr_to_cat.items():
                cursor.execute("SELECT id FROM categories WHERE name = ?", (cat_name,))
                row = cursor.fetchone()
                if row:
                    cat_id = row[0]
                    cursor.execute("UPDATE products SET category_id = ? WHERE name LIKE ?", (cat_id, f"%{substr}%"))

        reconcile_existing_products()
        # Также попробуем заполнить КБЖУ для существующих товаров по подстрокам в имени
        substr_to_kbju = {
            "Мандари": (20.0, 1.0, 0.5, 120.0),
            "Апельс": (11.0, 0.9, 0.2, 47.0),
            "виноград": (18.0, 0.6, 0.4, 90.0),
            "Груши": (16.0, 0.5, 0.3, 80.0),
            "Киви": (14.0, 1.2, 0.6, 70.0),
            "Молоко": (5.0, 3.2, 3.2, 60.0),
            "Сыр": (1.0, 25.0, 33.0, 400.0),
            "Кури": (0.0, 31.0, 3.6, 165.0),
            "Шоколад": (56.0, 7.0, 31.0, 540.0),
        }
        for substr, (k_val, b_val, j_val, u_val) in substr_to_kbju.items():
            cursor.execute(
                "UPDATE products SET k = ?, b = ?, j = ?, u = ? WHERE name LIKE ?",
                (k_val, b_val, j_val, u_val, f"%{substr}%"),
            )

        conn.commit()
        conn.close()
        return

    print("Инициализация базы данных...")

    # Если таблица categories уже содержит записи, не будем вставлять их снова — во избежание дубликатов
    cursor.execute("SELECT COUNT(*) FROM categories")
    cats_count = cursor.fetchone()[0]

    # Категории
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

    if cats_count == 0:
        cursor.executemany("INSERT OR IGNORE INTO categories (name) VALUES (?)", categories)
    else:
        print(f"Категории уже присутствуют в базе (count={cats_count}), пропускаем вставку категорий")

    # Товары — вставляем/обновляем, подставляя фактический category_id по имени категории
    products_data = [
        ("Мандарины отборные", "600 г • Дарим карточку • -12%", 219.0, "https://images.unsplash.com/photo-1611080626919-7cf5a9dbab5b?w=400", "Овощи и фрукты", 20.0, 1.0, 0.5, 120.0),
        ("Апельсины", "1 кг • Дарим карточку • -25%", 149.0, "https://images.unsplash.com/photo-1502741126161-b048400d27b8?w=400", "Овощи и фрукты", 11.0, 0.9, 0.2, 47.0),
        ("Белый виноград Shine Muscat", "500 г • -10%", 449.0, "https://images.unsplash.com/photo-1567306226416-28f0efdc88ce?w=400", "Овощи и фрукты", 18.0, 0.6, 0.4, 90.0),
        ("Груши Пакхам", "500 г • -15%", 175.0, "https://images.unsplash.com/photo-1574226516831-e1dff420e3f7?w=400", "Овощи и фрукты", 16.0, 0.5, 0.3, 80.0),
        ("Киви Артфрут Gold", "3 шт • Дарим карточку • -14%", 170.0, "https://images.unsplash.com/photo-1574226516831-e1dff420e3f7?w=400", "Овощи и фрукты", 14.0, 1.2, 0.6, 70.0),
        ("Молоко Самокат 3.2%", "1 л", 89.0, "https://images.unsplash.com/photo-1582719478149-59d4b7f0f5d3?w=400", "Молоко, яйца и сыр", 5.0, 3.2, 3.2, 60.0),
        ("Сыр твердый", "200 г", 320.0, "https://images.unsplash.com/photo-1544025162-d76694265947?w=400", "Молоко, яйца и сыр", 1.0, 25.0, 33.0, 400.0),
        ("Куриное филе", "500 г", 299.0, "https://images.unsplash.com/photo-1604908177522-4d9aef0d5c7a?w=400", "Мясо и рыба", 0.0, 31.0, 3.6, 165.0),
        ("Шоколад молочный", "100 г • -20%", 89.0, "https://images.unsplash.com/photo-1549880338-65ddcdfd017b?w=400", "Сладкое и снеки", 56.0, 7.0, 31.0, 540.0),
    ]

    for name, desc, price, img, cat_name, k_val, b_val, j_val, u_val in products_data:
        # получаем id категории по имени
        cursor.execute("SELECT id FROM categories WHERE name = ?", (cat_name,))
        row = cursor.fetchone()
        if row:
            cat_id = row[0]
        else:
            # если категории нет (маловероятно), вставим её и возьмём id
            cursor.execute("INSERT INTO categories (name) VALUES (?)", (cat_name,))
            cat_id = cursor.lastrowid

        # пытаемся обновить существующий товар по имени
        cursor.execute(
            "UPDATE products SET description = ?, price = ?, image_url = ?, category_id = ?, k = ?, b = ?, j = ?, u = ? WHERE name = ?",
            (desc, price, img, cat_id, k_val, b_val, j_val, u_val, name),
        )
        if cursor.rowcount == 0:
            # если ничего не обновлено — вставляем новый товар
            cursor.execute(
                "INSERT INTO products (name, description, price, image_url, category_id, k, b, j, u) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, desc, price, img, cat_id, k_val, b_val, j_val, u_val),
            )

    conn.commit()
    conn.close()


@app.on_event("startup")
async def startup_event():
    init_db()


@app.get("/")
async def index(
    request: Request,
    category_id: int | None = Query(None),
    search: str | None = Query(None),
    current_user=Depends(get_current_user_or_none),
    db: Session = Depends(get_db),
):
    categories = db.query(Category).all()
    query = db.query(Product)
    if category_id:
        query = query.filter(Product.category_id == category_id)
    # регистронезависимый поиск: разбиваем на слова и ищем в name или description (AND по токенам)
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

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "categories": categories,
            "products": products,
            "current_user": current_user,
            "search_query": search or "",
            "selected_category_id": category_id,  # ← добавили это
        },
    )


@app.get("/products/{product_id}")
async def product_detail(
    request: Request,
    product_id: int,
    current_user=Depends(get_current_user_or_none),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return templates.TemplateResponse(
        "product.html", {"request": request, "product": product, "current_user": current_user}
    )


@app.get("/cart")
async def cart_page(
    request: Request,
    session_id: str | None = Query(None),
    current_user=Depends(get_current_user_or_none),
    db: Session = Depends(get_db),
):
    from routers.cart import get_cart  # late import to avoid circular

    cart_items = get_cart(current_user=current_user, session_id=session_id, db=db)
    total_price = sum(item.product.price * item.quantity for item in cart_items)

    return templates.TemplateResponse(
        "cart.html",
        {
            "request": request,
            "cart_items": cart_items,
            "total_price": total_price,
            "current_user": current_user,
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)