import sqlite3
import time

# Попытка подключиться с таймаутом
for attempt in range(5):
    try:
        conn = sqlite3.connect('store.db', timeout=10)
        break
    except sqlite3.OperationalError:
        print('DB locked, retrying...')
        time.sleep(1)
else:
    raise SystemExit('Не удалось подключиться к БД')

cur = conn.cursor()

# Явная миграция таблиц истории заказов
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NULL,
        session_id TEXT NULL,
        status TEXT NOT NULL DEFAULT 'created',
        total REAL NOT NULL DEFAULT 0,
        delivery_address TEXT NULL,
        created_at INTEGER NOT NULL
    )
    """
)
cur.execute(
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

# Backfill истории заказов: пока пустой по требованиям
print('Backfill order history: skipped (empty by design)')

# Список подстрок -> имя категории
mapping = {
    'Мандари': 'Овощи и фрукты',
    'Апельс': 'Овощи и фрукты',
    'виноград': 'Овощи и фрукты',
    'Груши': 'Овощи и фрукты',
    'Киви': 'Овощи и фрукты',
    'Молоко': 'Молоко, яйца и сыр',
    'Сыр': 'Молоко, яйца и сыр',
    'Кури': 'Мясо и рыба',
    'Шоколад': 'Сладкое и снеки',
}

# Получаем маппинг категорий
cats = {row[1]: row[0] for row in cur.execute('SELECT id, name FROM categories')}
print('Категории (name->id):', cats)

updated_total = 0
for substr, cat_name in mapping.items():
    cat_id = cats.get(cat_name)
    if not cat_id:
        print('Категория не найдена:', cat_name)
        continue
    try:
        cur.execute('UPDATE products SET category_id = ? WHERE name LIKE ?', (cat_id, f'%{substr}%'))
        cnt = cur.rowcount
        updated_total += cnt
        print(f"Обновлено {cnt} записей для подстроки '{substr}' -> категория '{cat_name}' (id={cat_id})")
    except sqlite3.OperationalError as e:
        print('Ошибка при обновлении для', substr, e)

conn.commit()
print('Всего обновлено:', updated_total)

print('\nТекущие товары и их категории:')
for r in cur.execute("SELECT p.id, p.name, c.name FROM products p LEFT JOIN categories c ON p.category_id = c.id ORDER BY p.id"):
    print(r)

conn.close()
