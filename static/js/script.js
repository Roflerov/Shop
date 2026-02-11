function getToken() {
    // теперь фронтенд не использует localStorage для токена в cookie-only модели
    return null;
}

function getSessionId() {
    let sid = localStorage.getItem("session_id");
    if (!sid) {
        sid = crypto.randomUUID();
        localStorage.setItem("session_id", sid);
    }
    return sid;
}

function getHeaders(withAuth = true) {
    // Убираем Authorization header: сервер будет читать cookie
    const headers = { "Content-Type": "application/json" };
    return headers;
}

// Загрузим список категорий один раз и сохраним в мапу
window.categoriesMap = {};
(async function loadCategories(){
    try{
        const res = await fetch('/products/categories/');
        if(res.ok){
            const cats = await res.json();
            cats.forEach(c=> window.categoriesMap[c.id]=c.name);
        }
    }catch(e){console.warn('Не удалось загрузить категории',e)}
})();

async function addToCart(productId, quantity=1) {
    const data = { product_id: productId, quantity: quantity };
    const sid = getSessionId();
    try {
        const res = await fetch(`/cart/?session_id=${sid}`, {
            method: "POST",
            headers: getHeaders(),
            credentials: 'same-origin',
            body: JSON.stringify(data),
        });
        if (res.ok) {
            alert("Добавлено в корзину!");
        } else {
            alert("Ошибка добавления");
        }
    } catch (e) {
        console.error(e);
        alert("Ошибка сети");
    }
}

async function removeFromCart(itemId) {
    const sid = getSessionId();
    try {
        const res = await fetch(`/cart/${itemId}?session_id=${sid}`, {
            method: "DELETE",
            headers: getHeaders(),
            credentials: 'same-origin',
        });
        if (res.ok) {
            location.reload();
        } else {
            alert("Не удалось удалить");
        }
    } catch (e) {
        alert("Ошибка");
    }
}

async function checkout() {
    const addrEl = document.getElementById("delivery_address");
    const address = addrEl ? addrEl.value.trim() : "";
    if (!address) {
        alert("Введите адрес доставки");
        return;
    }
    const data = { delivery_address: address };
    const sid = getSessionId();
    try {
        const res = await fetch(`/cart/checkout/?session_id=${sid}`, {
            method: "POST",
            headers: getHeaders(),
            credentials: 'same-origin',
            body: JSON.stringify(data),
        });
        if (res.ok) {
            alert("Заказ оформлен! Корзина очищена.");
            location.href = "/";
        } else {
            alert("Ошибка оформления");
        }
    } catch (e) {
        alert("Ошибка сети");
    }
}

async function login() {
    const usernameEl = document.getElementById("username");
    const passwordEl = document.getElementById("password");
    const username = usernameEl ? usernameEl.value.trim() : "";
    const password = passwordEl ? passwordEl.value.trim() : "";
    if (!username || !password) return alert("Заполните поля");

    try {
        const res = await fetch("/users/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: 'same-origin',
            body: JSON.stringify({ username, password }),
        });
        const data = await res.json();
        if (res.ok && data.access_token) {
            // Сервер установит HttpOnly cookie; не сохраняем токен в localStorage
            location.href = "/";
        } else {
            alert(data.detail || "Ошибка входа");
        }
    } catch (e) {
        alert("Ошибка сети");
    }
}

async function register() {
    const usernameEl = document.getElementById("username");
    const passwordEl = document.getElementById("password");
    const addressEl = document.getElementById("delivery_address");
    const username = usernameEl ? usernameEl.value.trim() : "";
    const password = passwordEl ? passwordEl.value.trim() : "";
    const address = addressEl ? addressEl.value.trim() : "";

    if (!username || !password) return alert("Логин и пароль обязательны");

    try {
        const res = await fetch("/users/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: 'same-origin',
            body: JSON.stringify({ username, password, delivery_address: address || null }),
        });
        if (res.ok) {
            alert("Регистрация успешна! Теперь войдите.");
            location.href = "/login";
        } else {
            const err = await res.json();
            alert(err.detail || "Ошибка регистрации");
        }
    } catch (e) {
        alert("Ошибка сети");
    }
}
function goToCart() {
    const sid = getSessionId();  // функция уже есть в твоём script.js
    window.location.href = `/cart?session_id=${sid}`;
}
// Автокомплит адреса с Yandex Geosuggest
const suggestInput = document.querySelector('.suggest-input');
const suggestResults = document.getElementById('suggest-results');

if (suggestInput) {
    suggestInput.addEventListener('input', debounce(suggestAddresses, 300));
}

function debounce(func, delay) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), delay);
    };
}

async function suggestAddresses() {
    const query = suggestInput.value.trim();
    if (query.length < 3) {
        suggestResults.innerHTML = '';
        suggestResults.style.display = 'none';
        return;
    }

    const apiKey = 'YOUR_YANDEX_API_KEY';  // Замени на свой ключ!!!
    const url = `https://suggest-maps.yandex.ru/v1/suggest?apikey=${apiKey}&text=${encodeURIComponent(query)}&lang=ru_RU&types=house,street,district,metro,locality`;

    try {
        const res = await fetch(url);
        const data = await res.json();
        suggestResults.innerHTML = '';
        suggestResults.style.display = 'block';

        if (data.results && data.results.length > 0) {
            data.results.forEach(item => {
                const div = document.createElement('div');
                div.classList.add('suggest-item');
                div.textContent = item.title.text;
                div.addEventListener('click', () => {
                    suggestInput.value = item.title.text;
                    suggestResults.innerHTML = '';
                    suggestResults.style.display = 'none';
                });
                suggestResults.appendChild(div);
            });
        } else {
            suggestResults.innerHTML = '<div class="suggest-item no-results">Нет предложений</div>';
        }
    } catch (e) {
        console.error('Ошибка автокомплита:', e);
    }
}

// Закрытие дропдауна при клике вне
document.addEventListener('click', (e) => {
    if (suggestInput && suggestResults) {
        if (!suggestInput.contains(e.target) && !suggestResults.contains(e.target)) {
            suggestResults.style.display = 'none';
        }
    }
});

async function updateQuantity(itemId, change) {
    const sid = getSessionId();
    const qtyInput = event.target.parentElement.querySelector('.qty-input');
    let currentQty = parseInt(qtyInput.value);
    let newQty = currentQty + change;

    if (newQty < 1) newQty = 1;

    try {
        const res = await fetch(`/cart/update`, {
            method: "POST",
            headers: getHeaders(),
            credentials: 'same-origin',
            body: JSON.stringify({
                item_id: itemId,
                quantity: newQty,
                session_id: sid
            })
        });

        if (res.ok) {
            location.reload();  // перезагружаем страницу для обновления цен
        } else {
            alert("Не удалось обновить количество");
        }
    } catch (e) {
        alert("Ошибка сети");
    }
}

async function logout() {
    try {
        const res = await fetch('/users/logout', { method: 'POST', credentials: 'same-origin' });
        // сервер удалит HttpOnly cookie
        if (res.ok) {
            alert('Вы вышли');
            window.location.href = '/';
        } else {
            alert('Ошибка при выходе');
        }
    } catch (e) {
        alert('Ошибка сети');
    }
}

// Открыть модальное окно продукта
async function openProductModal(productId) {
    try {
        let res;
        try {
            res = await fetch(`/api/products/${productId}`, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' });
        } catch (e) {
            console.warn('Primary API fetch failed, will try fallback', e);
            res = null;
        }

        if (!res || !res.ok) {
            // попытка fallback на /products/{id} с Accept: application/json
            try {
                const res2 = await fetch(`/products/${productId}`, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' });
                if (res2.ok) {
                    res = res2;
                } else {
                    const text = await res2.text().catch(()=>'<no body>');
                    console.error('Fallback fetch failed', productId, res2.status, text);
                    alert('Не удалось загрузить товар (статус ' + res2.status + ')');
                    return;
                }
            } catch (e2) {
                console.error('Both primary and fallback fetch failed', e2);
                alert('Не удалось загрузить товар');
                return;
            }
        }

        let product;
        try {
            product = await res.json();
        } catch (e) {
            const text = await res.text().catch(()=>'<no body>');
            console.error('Failed to parse product JSON', e, text);
            alert('Ошибка обработки данных товара');
            return;
        }

        document.getElementById('modal-image').src = product.image_url || '/static/img/placeholder.png';
        document.getElementById('modal-image').alt = product.name;
        document.getElementById('modal-title').textContent = product.name;
        document.getElementById('modal-desc').textContent = product.description || '';
        // заполняем категорию через ранее загруженную мапу
        const catName = window.categoriesMap[product.category_id] || '';
        const catEl = document.getElementById('modal-category');
        if (catEl) catEl.textContent = catName;
        // Форматируем и показываем КБЖУ
        const k = product.k != null ? product.k : '-';
        const b = product.b != null ? product.b : '-';
        const j = product.j != null ? product.j : '-';
        const u = product.u != null ? product.u : '-';
        document.getElementById('modal-kbju').innerHTML =
            `<div class="kbju-badge">К: <strong>${k}</strong></div>` +
            `<div class="kbju-badge">Б: <strong>${b}</strong></div>` +
            `<div class="kbju-badge">Ж: <strong>${j}</strong></div>` +
            `<div class="kbju-badge">У: <strong>${u}</strong></div>`;
        document.getElementById('modal-price').textContent = product.price + ' ₽';
        const qtyInput = document.getElementById('modal-qty');
        qtyInput.value = 1;
        document.getElementById('modal-qty-decr').onclick = ()=>{
            const v = Math.max(1, parseInt(qtyInput.value || '1') - 1);
            qtyInput.value = v;
        };
        document.getElementById('modal-qty-incr').onclick = ()=>{
            const v = Math.max(1, parseInt(qtyInput.value || '1') + 1);
            qtyInput.value = v;
        };
        const addBtn = document.getElementById('modal-add-btn');
        addBtn.onclick = ()=>{ addToCart(product.id, parseInt(qtyInput.value||'1')); closeProductModal(); };
        const modal = document.getElementById('product-modal');
        // Принудительно выставляем inline-стили, чтобы избежать проблем с кэшем или конфликтующими правилами
        const modalCard = modal.querySelector('.modal-card');
        const modalBody = modal.querySelector('.modal-body');
        const modalMedia = modal.querySelector('.modal-media');
        const modalInfo = modal.querySelector('.modal-info');
        if (modalCard) {
            modalCard.style.display = 'flex';
            modalCard.style.flexDirection = 'column';
            modalCard.style.alignItems = 'stretch';
            modalCard.style.overflow = 'hidden';
            modalCard.style.padding = '18px 20px';
            modalCard.style.maxWidth = '560px';
        }
        if (modalBody) {
            modalBody.style.display = 'flex';
            modalBody.style.flexDirection = 'column';
            modalBody.style.gap = '12px';
            modalBody.style.padding = '0';
        }
        if (modalMedia) {
            modalMedia.style.width = '100%';
        }
        if (modalInfo) {
            modalInfo.style.width = '100%';
            modalInfo.style.padding = '18px 6px 22px 6px';
            modalInfo.style.textAlign = 'center';
        }
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden','false');
    } catch (e) {
        console.error('openProductModal error:', e);
        alert('Ошибка загрузки товара');
    }
}

function closeProductModal() {
    const modal = document.getElementById('product-modal');
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden','true');
}

// Делегирование кликов: ловим клики на карточках, если кликнули по имени или картинке — открываем модал
document.addEventListener('click', function (e) {
    const card = e.target.closest('.product-card');
    if (!card) return;
    // если клик по img или по h3 a
    if (e.target.tagName === 'IMG' || e.target.closest('h3')) {
        e.preventDefault();
        const pid = card.dataset.productId || null;
        if (pid) {
            openProductModal(parseInt(pid));
            return;
        }
        // fallback: парсим href
        const a = card.querySelector('h3 a');
        if (a) {
            const href = a.getAttribute('href');
            const m = href && href.match(/\/products\/(\d+)/);
            if (m) {
                openProductModal(parseInt(m[1]));
            }
        }
    }
});
