import sys
import pathlib
root = pathlib.Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from fastapi.testclient import TestClient
import main
from database import SessionLocal
from models import Product
from sqlalchemy import or_, func

client = TestClient(main.app)

with SessionLocal() as db:
    p = db.query(Product).filter(Product.name.ilike('%Апельс%')).first()
    if not p:
        p = db.query(Product).first()
    if not p:
        print('No products in DB')
    else:
        print('db first product:', p.name)
        # прямой SQLAlchemy запрос (как в router)
        tokens = ['апельсины']
        q = db.query(Product)
        for t in tokens:
            t_low = t.lower()
            pattern = f"%{t_low}%"
            q = q.filter(
                or_(
                    func.lower(Product.name).like(pattern),
                    func.lower(Product.description).like(pattern),
                )
            )
        res = q.all()
        print('direct sqlalchemy count:', len(res))
        for r in res:
            print(' -', r.name)

        # HTTP endpoint
        r = client.get('/products/', params={'search': 'апельсины'})
        print('http status', r.status_code)
        try:
            js = r.json()
        except Exception as e:
            print('json parse error', e)
            js = None
        print('http result count', len(js) if isinstance(js, list) else 'not list')
        if isinstance(js, list) and js:
            print('first name:', js[0].get('name'))
