from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text
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


class CartItem(Base):
    __tablename__ = "cart_items"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)
    user = relationship("User", back_populates="cart_items")
    product = relationship("Product")