from pydantic import BaseModel
from typing import Optional


class CategoryOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    password: str
    delivery_address: Optional[str] = None


class UserInDB(BaseModel):
    id: int
    username: str
    delivery_address: Optional[str]

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class ProductOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    image_url: Optional[str]
    category_id: int
    k: Optional[float]
    b: Optional[float]
    j: Optional[float]
    u: Optional[float]

    class Config:
        from_attributes = True


class CartItemBase(BaseModel):
    product_id: int
    quantity: int = 1


class CartItemOut(CartItemBase):
    id: int
    product: ProductOut

    class Config:
        from_attributes = True


class Checkout(BaseModel):
    delivery_address: str