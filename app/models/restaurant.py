from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import TimestampMixin


class Restaurant(TimestampMixin, Base):
    __tablename__ = "restaurants"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    cuisine_type = Column(String(100), nullable=False, index=True)
    address = Column(String(255), nullable=False)
    latitude = Column(Float(53), nullable=False)
    longitude = Column(Float(53), nullable=False)
    opening_time = Column(Time, nullable=False)
    closing_time = Column(Time, nullable=False)
    is_temporarily_closed = Column(Boolean, default=False, nullable=False)
    delivery_radius_km = Column(Float, default=5, nullable=False)
    min_order_value = Column(Numeric(10, 2), default=0, nullable=False)
    avg_preparation_minutes = Column(Integer, default=20, nullable=False)
    average_rating = Column(Float, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    owner = relationship("User", back_populates="restaurants")
    categories = relationship("MenuCategory", back_populates="restaurant", cascade="all, delete-orphan")
    menu_items = relationship("MenuItem", back_populates="restaurant")
    orders = relationship("Order", back_populates="restaurant")


class MenuCategory(TimestampMixin, Base):
    __tablename__ = "menu_categories"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)

    restaurant = relationship("Restaurant", back_populates="categories")
    items = relationship("MenuItem", back_populates="category")


class MenuItem(TimestampMixin, Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("menu_categories.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    is_veg = Column(Boolean, default=True, nullable=False)
    packaging_charge = Column(Numeric(10, 2), default=0, nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)  # soft delete

    restaurant = relationship("Restaurant", back_populates="menu_items")
    category = relationship("MenuCategory", back_populates="items")
