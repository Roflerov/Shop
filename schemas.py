from pydantic import BaseModel, Field
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
    popularity: int

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


class CartUpdateRequest(BaseModel):
    item_id: int
    quantity: int = Field(ge=1)
    session_id: Optional[str] = None


class OrderCreate(BaseModel):
    delivery_address: Optional[str] = None
    status: str = "created"


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: float
    created_at: int
    product: ProductOut

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    user_id: Optional[int]
    session_id: Optional[str]
    status: str
    total: float
    delivery_address: Optional[str]
    items_json: Optional[str]
    created_at: int
    items: list[OrderItemOut]

    class Config:
        from_attributes = True


class MLTrainingInteractionOut(BaseModel):
    id: int
    user_id: Optional[int]
    session_id: Optional[str]
    product_id: int
    category_id: Optional[int]
    product_popularity: int
    event_type: str
    implicit_weight: float
    placement: Optional[str]
    source_product_id: Optional[int]
    created_at: int

    class Config:
        from_attributes = True


class MLTrainingInteractionsStats(BaseModel):
    total_events: int
    unique_products: int
    unique_users: int
    unique_sessions: int
    samples_needed_for_1000: int
    event_types: dict[str, int]
    placements: dict[str, int]


class MLTrainingBackfillResult(BaseModel):
    events_added: int
    purchases_added: int