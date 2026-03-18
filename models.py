from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    products = relationship("Product", back_populates="category")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    delivery_address = Column(Text, nullable=True)
    cart_items = relationship("CartItem", back_populates="user")
    orders = relationship("Order", back_populates="user")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    price = Column(Float)
    image_url = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    category = relationship("Category", back_populates="products")
    # КБЖУ: К (углеводы), Б (белки), Ж (жиры), У (ккал)
    k = Column(Float, nullable=True)
    b = Column(Float, nullable=True)
    j = Column(Float, nullable=True)
    u = Column(Float, nullable=True)
    popularity = Column(Integer, nullable=False, default=0)


class CartItem(Base):
    __tablename__ = "cart_items"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)
    user = relationship("User", back_populates="cart_items")
    product = relationship("Product")


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="created")
    total = Column(Float, nullable=False, default=0.0)
    delivery_address = Column(Text, nullable=True)
    items_json = Column(Text, nullable=True)
    created_at = Column(Integer, nullable=False)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False, default=0.0)
    created_at = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class RecommendationEvent(Base):
    __tablename__ = "recommendation_events"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=True)
    placement = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    source_product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    created_at = Column(Integer, nullable=False)


class MLTrainingInteraction(Base):
    __tablename__ = "ml_training_interactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    category_id = Column(Integer, nullable=True)
    product_popularity = Column(Integer, nullable=False, default=0)
    event_type = Column(String(32), nullable=False, index=True)
    implicit_weight = Column(Float, nullable=False)
    placement = Column(String(32), nullable=True, index=True)
    source_product_id = Column(Integer, nullable=True, index=True)
    created_at = Column(Integer, nullable=False, index=True)
