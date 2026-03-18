import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request

DB_PATH = "store.db"
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "catalog_image_cache.json")
USER_AGENT = "ShopCatalogSeeder/1.0 (Wikimedia Commons image resolver)"

CATEGORY_TARGETS = {
    "Овощи и фрукты": [
        "Томаты сливовидные", "Огурцы короткоплодные", "Картофель молодой", "Морковь мытая", "Лук репчатый", "Чеснок свежий",
        "Капуста белокочанная", "Брокколи", "Цветная капуста", "Перец болгарский красный", "Кабачки", "Баклажаны",
        "Тыква мускатная", "Свёкла столовая", "Яблоки Гала", "Бананы", "Апельсины", "Мандарины", "Груши Конференция",
        "Виноград зелёный", "Киви", "Лимоны", "Укроп свежий", "Петрушка свежая", "Салат Айсберг",
    ],
    "Молоко, яйца и сыр": [
        "Молоко 2.5%", "Молоко 3.2%", "Кефир 1%", "Кефир 2.5%", "Ряженка 4%", "Йогурт греческий натуральный",
        "Йогурт клубничный", "Сметана 15%", "Сливки 10%", "Творог 5%", "Творог 9%", "Масло сливочное 82.5%",
        "Сыр Гауда", "Сыр Моцарелла", "Сыр Чеддер", "Сыр Фета", "Сыр Сулугуни", "Яйца куриные С1 10 шт",
        "Яйца куриные С0 10 шт", "Яйца перепелиные 20 шт", "Айран", "Биойогурт натуральный", "Молоко безлактозное",
        "Сгущённое молоко", "Сыр творожный сливочный",
    ],
    "Мясо и рыба": [
        "Куриное филе охлаждённое", "Бедро куриное без кости", "Филе индейки", "Говядина для тушения", "Фарш говяжий",
        "Свинина шея", "Свинина карбонад", "Филе лосося", "Филе форели", "Филе трески", "Филе минтая",
        "Стейк тунца", "Скумбрия охлаждённая", "Сельдь слабосолёная", "Креветки очищенные", "Мидии в створках",
        "Кальмар кольца", "Крылья куриные", "Филе утки", "Кролик тушка", "Печень говяжья", "Печень куриная",
        "Колбаски молочные", "Бекон сырокопчёный", "Крабовые палочки",
    ],
    "Хлеб и выпечка": [
        "Багет французский", "Хлеб ржаной", "Хлеб цельнозерновой", "Хлеб Бородинский", "Чиабатта", "Круассан сливочный",
        "Булочка с кунжутом", "Пита", "Лаваш тонкий", "Тортилья пшеничная", "Бриошь", "Хлеб тостовый",
        "Булочки зерновые", "Пончик сахарный", "Улитка с корицей", "Маффин ванильный", "Пирог вишнёвый кусок",
        "Штрудель яблочный", "Слойка с сыром", "Тесто для пиццы", "Фокачча", "Гренки чесночные", "Сухари классические",
        "Гриссини", "Сушки ванильные",
    ],
    "Готовая еда": [
        "Борщ домашний", "Суп куриный с лапшой", "Суп гороховый", "Салат Цезарь", "Салат Оливье", "Салат Греческий",
        "Пюре с котлетой", "Гречка с курицей", "Паста Болоньезе", "Рис с овощами", "Плов с курицей", "Гуляш говяжий",
        "Голубцы", "Перцы фаршированные", "Пельмени отварные", "Вареники с картофелем", "Блины с мясом",
        "Блины с творогом", "Суши-сет мини", "Шаурма с курицей", "Лазанья", "Курица карри с рисом",
        "Омлет с сыром", "Сырники", "Рагу овощное",
    ],
    "Сладкое и снеки": [
        "Шоколад молочный плитка", "Шоколад тёмный 70%", "Шоколад белый", "Батончик Snickers", "Батончик Twix",
        "Батончик Bounty", "Kinder Bueno", "Вафли ванильные", "Чипсы сметана и лук", "Чипсы паприка", "Попкорн карамель",
        "Попкорн солёный", "Печенье овсяное", "Печенье с шоколадной крошкой", "Пряники медовые", "Мармелад фруктовый",
        "Жевательные мишки", "Зефир ванильный", "Халва подсолнечная", "Козинаки кунжутные", "Ореховая смесь",
        "Арахис солёный", "Фисташки солёные", "Крекеры сырные", "Батончик мюсли",
    ],
    "Напитки": [
        "Вода негазированная 0.5", "Вода газированная 0.5", "Вода минеральная", "Кола 1 л", "Сок апельсиновый",
        "Сок яблочный", "Сок томатный", "Морс ягодный", "Чай холодный лимон", "Чай холодный персик", "Кофе американо",
        "Капучино готовый", "Какао напиток", "Зелёный чай бутылка", "Чёрный чай бутылка", "Лимонад тархун",
        "Лимонад цитрус", "Комбуча классическая", "Энергетический напиток", "Изотоник апельсин", "Милкшейк ванильный",
        "Смузи ягодный", "Смузи манго", "Кокосовая вода", "Квас хлебный",
    ],
    "Бакалея": [
        "Рис длиннозёрный", "Гречка ядрица", "Овсяные хлопья", "Макароны спагетти", "Макароны пенне", "Чечевица красная",
        "Горох колотый", "Нут", "Фасоль красная", "Мука пшеничная", "Мука ржаная", "Сахар белый", "Соль морская",
        "Масло подсолнечное", "Масло оливковое", "Томатная паста", "Томаты консервированные", "Кукуруза консервированная",
        "Горошек консервированный", "Тунец консервированный", "Майонез классический", "Кетчуп томатный", "Соус соевый",
        "Смесь специй универсальная", "Мёд цветочный",
    ],
}

CATEGORY_ALIASES = {
    "овощи и фрукты": "Овощи и фрукты",
    "молоко, яица, сыр": "Молоко, яйца и сыр",
    "молоко, яйца и сыр": "Молоко, яйца и сыр",
    "мясо и рыба": "Мясо и рыба",
    "хлеб и выпечка": "Хлеб и выпечка",
    "готовая еда": "Готовая еда",
    "сладкое и снеки": "Сладкое и снеки",
    "напитки": "Напитки",
    "бакалея": "Бакалея",
}

BASE_NUTRITION = {
    "Овощи и фрукты": (12.0, 1.1, 0.4, 65.0),
    "Молоко, яйца и сыр": (4.5, 10.5, 9.0, 150.0),
    "Мясо и рыба": (1.0, 19.0, 8.5, 165.0),
    "Хлеб и выпечка": (47.0, 7.5, 5.5, 280.0),
    "Готовая еда": (13.0, 8.5, 9.0, 190.0),
    "Сладкое и снеки": (52.0, 5.0, 18.0, 395.0),
    "Напитки": (9.0, 0.8, 0.3, 45.0),
    "Бакалея": (54.0, 8.0, 3.5, 305.0),
}

BASE_PRICE = {
    "Овощи и фрукты": 109.0,
    "Молоко, яйца и сыр": 129.0,
    "Мясо и рыба": 299.0,
    "Хлеб и выпечка": 89.0,
    "Готовая еда": 199.0,
    "Сладкое и снеки": 99.0,
    "Напитки": 79.0,
    "Бакалея": 119.0,
}


CATEGORY_CONTEXT = {
    "Овощи и фрукты": "fruit vegetable food",
    "Молоко, яйца и сыр": "dairy cheese egg food",
    "Мясо и рыба": "meat fish seafood food",
    "Хлеб и выпечка": "bread bakery pastry food",
    "Готовая еда": "dish meal food",
    "Сладкое и снеки": "snack candy dessert food",
    "Напитки": "drink beverage",
    "Бакалея": "grocery dry food",
}

PHRASE_OVERRIDES = {
    "Томаты сливовидные": ["plum tomato"],
    "Огурцы короткоплодные": ["cucumber"],
    "Картофель молодой": ["new potato"],
    "Морковь мытая": ["carrot"],
    "Лук репчатый": ["onion"],
    "Чеснок свежий": ["garlic"],
    "Капуста белокочанная": ["white cabbage"],
    "Перец болгарский красный": ["red bell pepper"],
    "Тыква мускатная": ["butternut squash"],
    "Свёкла столовая": ["beetroot"],
    "Яблоки Гала": ["gala apple"],
    "Груши Конференция": ["conference pear"],
    "Виноград зелёный": ["green grape"],
    "Укроп свежий": ["dill herb"],
    "Петрушка свежая": ["parsley herb"],
    "Салат Айсберг": ["iceberg lettuce"],
    "Ряженка 4%": ["ryazhenka fermented baked milk"],
    "Йогурт греческий натуральный": ["greek yogurt"],
    "Сметана 15%": ["smetana sour cream"],
    "Творог 5%": ["tvorog cottage cheese"],
    "Творог 9%": ["tvorog cottage cheese"],
    "Масло сливочное 82.5%": ["butter"],
    "Сыр Гауда": ["gouda cheese"],
    "Сыр Моцарелла": ["mozzarella cheese"],
    "Сыр Чеддер": ["cheddar cheese"],
    "Сыр Фета": ["feta cheese"],
    "Сыр Сулугуни": ["sulguni cheese"],
    "Яйца куриные С1 10 шт": ["chicken eggs"],
    "Яйца куриные С0 10 шт": ["chicken eggs"],
    "Яйца перепелиные 20 шт": ["quail eggs"],
    "Айран": ["ayran drink"],
    "Биойогурт натуральный": ["plain yogurt"],
    "Молоко безлактозное": ["lactose free milk"],
    "Сгущённое молоко": ["condensed milk"],
    "Сыр творожный сливочный": ["cream cheese"],
    "Куриное филе охлаждённое": ["chicken fillet raw"],
    "Бедро куриное без кости": ["boneless chicken thigh"],
    "Филе индейки": ["turkey fillet raw"],
    "Говядина для тушения": ["beef stew meat raw"],
    "Фарш говяжий": ["ground beef raw"],
    "Свинина шея": ["pork neck raw"],
    "Свинина карбонад": ["pork loin raw"],
    "Филе лосося": ["salmon fillet raw"],
    "Филе форели": ["trout fillet raw"],
    "Филе трески": ["cod fillet raw"],
    "Филе минтая": ["pollock fillet raw"],
    "Стейк тунца": ["tuna steak raw"],
    "Скумбрия охлаждённая": ["mackerel raw"],
    "Сельдь слабосолёная": ["salted herring"],
    "Креветки очищенные": ["peeled shrimp"],
    "Мидии в створках": ["mussels shell"],
    "Кальмар кольца": ["calamari rings"],
    "Крылья куриные": ["chicken wings raw"],
    "Филе утки": ["duck breast raw"],
    "Кролик тушка": ["rabbit meat raw"],
    "Печень говяжья": ["beef liver raw"],
    "Печень куриная": ["chicken liver raw"],
    "Колбаски молочные": ["sausage"],
    "Бекон сырокопчёный": ["bacon"],
    "Крабовые палочки": ["imitation crab sticks"],
    "Багет французский": ["french baguette"],
    "Хлеб ржаной": ["rye bread"],
    "Хлеб цельнозерновой": ["whole grain bread"],
    "Хлеб Бородинский": ["borodinsky bread"],
    "Чиабатта": ["ciabatta bread"],
    "Круассан сливочный": ["croissant"],
    "Булочка с кунжутом": ["sesame bun"],
    "Пита": ["pita bread"],
    "Лаваш тонкий": ["lavash"],
    "Тортилья пшеничная": ["wheat tortilla"],
    "Бриошь": ["brioche"],
    "Хлеб тостовый": ["toast bread"],
    "Булочки зерновые": ["grain roll bread"],
    "Пончик сахарный": ["sugar doughnut"],
    "Улитка с корицей": ["cinnamon roll"],
    "Маффин ванильный": ["vanilla muffin"],
    "Пирог вишнёвый кусок": ["cherry pie slice"],
    "Штрудель яблочный": ["apple strudel"],
    "Слойка с сыром": ["cheese puff pastry"],
    "Тесто для пиццы": ["pizza dough"],
    "Фокачча": ["focaccia"],
    "Гренки чесночные": ["garlic croutons"],
    "Сухари классические": ["rusks bread"],
    "Гриссини": ["grissini breadsticks"],
    "Сушки ванильные": ["vanilla ring biscuit"],
    "Борщ домашний": ["borscht soup"],
    "Суп куриный с лапшой": ["chicken noodle soup"],
    "Суп гороховый": ["pea soup"],
    "Салат Цезарь": ["caesar salad"],
    "Салат Оливье": ["olivier salad"],
    "Салат Греческий": ["greek salad"],
    "Пюре с котлетой": ["mashed potatoes cutlet"],
    "Гречка с курицей": ["buckwheat chicken dish"],
    "Паста Болоньезе": ["spaghetti bolognese"],
    "Рис с овощами": ["vegetable rice dish"],
    "Плов с курицей": ["chicken pilaf"],
    "Гуляш говяжий": ["beef goulash"],
    "Голубцы": ["cabbage rolls"],
    "Перцы фаршированные": ["stuffed peppers"],
    "Пельмени отварные": ["pelmeni"],
    "Вареники с картофелем": ["vareniki potato"],
    "Блины с мясом": ["meat crepes"],
    "Блины с творогом": ["cottage cheese crepes"],
    "Суши-сет мини": ["sushi set"],
    "Шаурма с курицей": ["chicken shawarma"],
    "Лазанья": ["lasagna"],
    "Курица карри с рисом": ["chicken curry rice"],
    "Омлет с сыром": ["cheese omelette"],
    "Сырники": ["syrniki"],
    "Рагу овощное": ["vegetable stew"],
    "Шоколад молочный плитка": ["milk chocolate bar"],
    "Шоколад тёмный 70%": ["dark chocolate bar"],
    "Шоколад белый": ["white chocolate bar"],
    "Батончик Snickers": ["snickers bar"],
    "Батончик Twix": ["twix bar"],
    "Батончик Bounty": ["bounty bar"],
    "Kinder Bueno": ["kinder bueno"],
    "Вафли ванильные": ["wafer biscuit"],
    "Чипсы сметана и лук": ["potato chips"],
    "Чипсы паприка": ["paprika potato chips"],
    "Попкорн карамель": ["caramel popcorn"],
    "Попкорн солёный": ["salted popcorn"],
    "Печенье овсяное": ["oatmeal cookie"],
    "Печенье с шоколадной крошкой": ["chocolate chip cookie"],
    "Пряники медовые": ["honey gingerbread"],
    "Мармелад фруктовый": ["fruit jelly candy"],
    "Жевательные мишки": ["gummy bears"],
    "Зефир ванильный": ["vanilla marshmallow confectionery"],
    "Халва подсолнечная": ["sunflower halva"],
    "Козинаки кунжутные": ["sesame brittle"],
    "Ореховая смесь": ["mixed nuts"],
    "Арахис солёный": ["salted peanuts"],
    "Фисташки солёные": ["salted pistachios"],
    "Крекеры сырные": ["cheese crackers"],
    "Батончик мюсли": ["granola bar"],
    "Вода негазированная 0.5": ["still water bottle"],
    "Вода газированная 0.5": ["sparkling water bottle"],
    "Вода минеральная": ["mineral water bottle"],
    "Кола 1 л": ["cola bottle"],
    "Сок апельсиновый": ["orange juice"],
    "Сок яблочный": ["apple juice"],
    "Сок томатный": ["tomato juice"],
    "Морс ягодный": ["berry fruit drink"],
    "Чай холодный лимон": ["iced tea lemon"],
    "Чай холодный персик": ["iced tea peach"],
    "Кофе американо": ["americano coffee"],
    "Капучино готовый": ["cappuccino drink"],
    "Какао напиток": ["cocoa drink"],
    "Зелёный чай бутылка": ["green tea bottle"],
    "Чёрный чай бутылка": ["black tea bottle"],
    "Лимонад тархун": ["tarragon lemonade"],
    "Лимонад цитрус": ["citrus lemonade"],
    "Комбуча классическая": ["kombucha bottle"],
    "Энергетический напиток": ["energy drink can"],
    "Изотоник апельсин": ["isotonic drink orange"],
    "Милкшейк ванильный": ["vanilla milkshake"],
    "Смузи ягодный": ["berry smoothie"],
    "Смузи манго": ["mango smoothie"],
    "Кокосовая вода": ["coconut water"],
    "Квас хлебный": ["kvass bottle"],
    "Рис длиннозёрный": ["long grain rice"],
    "Гречка ядрица": ["buckwheat groats"],
    "Овсяные хлопья": ["rolled oats"],
    "Макароны спагетти": ["spaghetti pasta"],
    "Макароны пенне": ["penne pasta"],
    "Чечевица красная": ["red lentils"],
    "Горох колотый": ["split peas"],
    "Нут": ["chickpeas dry"],
    "Фасоль красная": ["red kidney beans dry"],
    "Мука пшеничная": ["wheat flour"],
    "Мука ржаная": ["rye flour"],
    "Сахар белый": ["white sugar"],
    "Соль морская": ["sea salt"],
    "Масло подсолнечное": ["sunflower oil bottle"],
    "Масло оливковое": ["olive oil bottle"],
    "Томатная паста": ["tomato paste"],
    "Томаты консервированные": ["canned tomatoes"],
    "Кукуруза консервированная": ["canned corn"],
    "Горошек консервированный": ["canned peas"],
    "Тунец консервированный": ["canned tuna"],
    "Майонез классический": ["mayonnaise jar"],
    "Кетчуп томатный": ["ketchup bottle"],
    "Соус соевый": ["soy sauce bottle"],
    "Смесь специй универсальная": ["mixed spice seasoning"],
    "Мёд цветочный": ["flower honey jar"],
}

STOPWORDS = {
    "fresh", "raw", "food", "drink", "dish", "meal", "classical", "natural",
    "with", "and", "the", "bottle", "bar", "slice", "mini", "plain",
}

def load_image_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_image_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def warm_cache_from_db(cursor, cache: dict) -> None:
    cursor.execute("SELECT name, image_url FROM products")
    for name, image_url in cursor.fetchall():
        if not image_url:
            continue
        if "placehold.co" in image_url:
            continue
        if name not in cache:
            cache[name] = {
                "query": "seeded_from_db",
                "url": image_url,
                "title": None,
                "ts": int(time.time()),
            }


def normalize_query_tokens(text: str) -> list[str]:
    text = text.lower().replace("ё", "e")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [token for token in text.split() if token and token not in STOPWORDS]


def candidate_queries(name: str, category_name: str) -> list[str]:
    if name in PHRASE_OVERRIDES:
        return PHRASE_OVERRIDES[name]

    cleaned = re.sub(r"\b\d+[\d.,%\s]*\b", " ", name.lower().replace("ё", "е"))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return [f"{cleaned} {CATEGORY_CONTEXT[category_name]}"]


def choose_best_result(results: list[dict], query: str) -> dict | None:
    query_tokens = set(normalize_query_tokens(query))
    best = None
    best_score = -1

    for result in results:
        title = result.get("title", "")
        title_tokens = set(normalize_query_tokens(title))
        overlap = len(query_tokens & title_tokens)
        score = overlap * 10 - len(title_tokens - query_tokens)
        if score > best_score:
            best_score = score
            best = result

    return best


def fetch_wikimedia_image(query: str) -> tuple[str | None, str | None]:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrnamespace": 6,
            "gsrsearch": query,
            "gsrlimit": 8,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": 800,
            "format": "json",
        }
    )
    url = f"https://commons.wikimedia.org/w/api.php?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))

    pages = list(data.get("query", {}).get("pages", {}).values())
    enriched = []
    for page in pages:
        imageinfo = page.get("imageinfo") or []
        if not imageinfo:
            continue
        enriched.append(
            {
                "title": page.get("title", ""),
                "thumburl": imageinfo[0].get("thumburl") or imageinfo[0].get("url"),
            }
        )

    best = choose_best_result(enriched, query)
    if not best:
        return None, None
    return best.get("thumburl"), best.get("title")


def make_image_url(name: str, category_name: str, cache: dict) -> str:
    cached = cache.get(name)
    if cached and cached.get("url"):
        return cached["url"]

    for query in candidate_queries(name, category_name):
        try:
            url, title = fetch_wikimedia_image(query)
            if url:
                cache[name] = {"query": query, "url": url, "title": title, "ts": int(time.time())}
                return url
        except Exception:
            continue

    fallback = f"https://placehold.co/800x600/png?text={urllib.parse.quote(name)}"
    cache[name] = {"query": None, "url": fallback, "title": None, "ts": int(time.time())}
    return fallback


def price_for(category: str, index: int) -> float:
    return round(BASE_PRICE[category] + (index % 5) * 17 + (index // 5) * 9, 2)


def kbju_for(category: str, index: int):
    k, b, j, u = BASE_NUTRITION[category]
    shift = (index % 5) - 2
    k = max(0.0, round(k + shift * 0.8, 2))
    b = max(0.0, round(b + shift * 0.5, 2))
    j = max(0.0, round(j + shift * 0.4, 2))
    u = max(0.0, round(u + shift * 6.0, 2))
    return k, b, j, u


def ensure_required_categories(cursor):
    cursor.execute("SELECT id, name FROM categories")
    existing = {name.casefold(): cid for cid, name in cursor.fetchall()}

    result = {}
    for alias, canonical in CATEGORY_ALIASES.items():
        key = canonical.casefold()
        if key not in existing:
            cursor.execute("INSERT INTO categories(name) VALUES (?)", (canonical,))
            existing[key] = cursor.lastrowid
        result[canonical] = existing[key]

    return result


def upsert_products(cursor, category_name: str, category_id: int, product_names: list[str], cache: dict):
    inserted = 0
    updated = 0

    for index, name in enumerate(product_names, start=1):
        price = price_for(category_name, index)
        k, b, j, u = kbju_for(category_name, index)
        image_url = make_image_url(name, category_name, cache)
        description = f"{category_name} • свежий товар"

        cursor.execute("SELECT id FROM products WHERE name = ?", (name,))
        row = cursor.fetchone()

        if row:
            cursor.execute(
                """
                UPDATE products
                SET description = ?, price = ?, image_url = ?, category_id = ?, k = ?, b = ?, j = ?, u = ?
                WHERE id = ?
                """,
                (description, price, image_url, category_id, k, b, j, u, row[0]),
            )
            updated += 1
        else:
            cursor.execute(
                """
                INSERT INTO products (name, description, price, image_url, category_id, k, b, j, u, popularity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (name, description, price, image_url, category_id, k, b, j, u),
            )
            inserted += 1

            if index % 5 == 0:
                save_image_cache(cache)
                print(f"  progress: {category_name} {index}/{len(product_names)}")

    return inserted, updated


def main():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    cache = load_image_cache()
    warm_cache_from_db(cursor, cache)

    # Базовая миграция нужных колонок
    cursor.execute("PRAGMA table_info(products)")
    cols = {r[1] for r in cursor.fetchall()}
    for col, definition in [
        ("k", "REAL"),
        ("b", "REAL"),
        ("j", "REAL"),
        ("u", "REAL"),
        ("popularity", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col not in cols:
            cursor.execute(f"ALTER TABLE products ADD COLUMN {col} {definition}")

    category_ids = ensure_required_categories(cursor)

    total_inserted = 0
    total_updated = 0

    for category_name, items in CATEGORY_TARGETS.items():
        if len(items) != 25:
            raise ValueError(f"В категории '{category_name}' должно быть ровно 25 товаров, сейчас {len(items)}")

        inserted, updated = upsert_products(
            cursor=cursor,
            category_name=category_name,
            category_id=category_ids[category_name],
            product_names=items,
            cache=cache,
        )
        total_inserted += inserted
        total_updated += updated
        print(f"{category_name}: inserted={inserted}, updated={updated}, total_target=25")

    conn.commit()
    save_image_cache(cache)

    print("\nПроверка количества товаров по категориям:")
    for category_name in CATEGORY_TARGETS.keys():
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM products p
            JOIN categories c ON c.id = p.category_id
            WHERE c.name = ?
            """,
            (category_name,),
        )
        count = cursor.fetchone()[0]
        print(f"- {category_name}: {count}")

    print(f"\nDONE: inserted={total_inserted}, updated={total_updated}")
    conn.close()


if __name__ == "__main__":
    main()
