from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import List

from database import get_db
from schemas import ProductOut, CategoryOut
from models import Product, Category

router = APIRouter(prefix="/products", tags=["Товары"])


@router.get("/", response_model=List[ProductOut])
def read_products(
    skip: int = 0,
    limit: int = 50,
    category_id: int | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Product)
    if category_id:
        query = query.filter(Product.category_id == category_id)
    # Для надёжной регистронезависимой фильтрации (особенно для кириллицы)
    # применим фильтрацию на стороне Python, а не SQL.
    if search:
        tokens = [t.strip().casefold() for t in search.split() if t.strip()]
        # Получаем кандидатов (включаем запасной буфер, чтобы иметь из чего выбирать)
        candidates = query.offset(skip).limit(limit if limit > 0 else 1000).all()
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
        return results

    return query.offset(skip).limit(limit).all()


@router.get("/{product_id}", response_model=ProductOut)
def read_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return product


@router.get("/categories/", response_model=List[CategoryOut])
def read_categories(db: Session = Depends(get_db)):
    return db.query(Category).all()