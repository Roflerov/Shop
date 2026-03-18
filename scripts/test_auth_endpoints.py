import sys
import pathlib
root = pathlib.Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from fastapi.testclient import TestClient
import main

client = TestClient(main.app)

username = "testuser123"
password = "testpass123"

# Попробуем удалить пользователя если уже существует (через прямой доступ к БД)
from database import SessionLocal
from models import User

with SessionLocal() as db:
    u = db.query(User).filter(User.username == username).first()
    if u:
        db.delete(u)
        db.commit()

# Регистрация
r = client.post("/users/register", json={"username": username, "password": password})
print('register status', r.status_code, r.text)

# Логин через OAuth2 form endpoint
r = client.post("/users/login", data={"username": username, "password": password})
print('login status', r.status_code, r.text)

# Получаем /users/me используя cookie, TestClient сохранит куки автоматически
r = client.get("/users/me")
print('/users/me', r.status_code, r.text)
