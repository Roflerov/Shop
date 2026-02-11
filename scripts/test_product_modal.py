import sys
import pathlib
root = pathlib.Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from fastapi.testclient import TestClient
import main
from database import SessionLocal
from models import Product

client = TestClient(main.app)

with SessionLocal() as db:
    p = db.query(Product).first()
    if not p:
        print('No products in DB')
    else:
        r = client.get(f'/api/products/{p.id}', headers={'Accept':'application/json'})
        print('status', r.status_code)
        print('json', r.json())
