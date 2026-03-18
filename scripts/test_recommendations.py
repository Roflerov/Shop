import uuid
import json
from urllib import request

BASE_URL = "http://127.0.0.1:8000"


def get_json(path: str):
    req = request.Request(f"{BASE_URL}{path}", method="GET")
    with request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def test_popularity_increment_and_metrics():
    products = get_json("/products/?limit=5")
    assert products, "Нет товаров для теста"

    target = products[0]
    before_popularity = target["popularity"]

    session_id = str(uuid.uuid4())
    payload = {"product_id": target["id"], "quantity": 1}

    req = request.Request(
        f"{BASE_URL}/cart/?session_id={session_id}&rec_source=home_popular",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10):
        pass

    target_after = get_json(f"/products/{target['id']}")
    assert target_after["popularity"] >= before_popularity + 1, (
        f"popularity не увеличился: before={before_popularity}, after={target_after['popularity']}"
    )

    metrics = get_json("/api/recommendations/metrics?hours=24")
    assert metrics["events_total"] >= 1, "Нет событий рекомендаций"

    print("OK: popularity increment + recommendation metrics")


if __name__ == "__main__":
    test_popularity_increment_and_metrics()
