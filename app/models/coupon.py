from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import TimestampMixin


class Coupon(TimestampMixin, Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # stored upper-case
    description = Column(String(255), nullable=True)
    discount_type = Column(String(20), nullable=False)  # Percentage | Flat
    discount_value = Column(Numeric(10, 2), nullable=False)
    max_discount = Column(Numeric(10, 2), nullable=True)
    min_order_value = Column(Numeric(10, 2), default=0, nullable=False)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=True, index=True)
    valid_from = Column(DateTime, nullable=False)
    valid_to = Column(DateTime, nullable=False)
    total_usage_limit = Column(Integer, nullable=True)
    per_user_limit = Column(Integer, nullable=True)
    first_order_only = Column(Boolean, default=False, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    restaurant = relationship("Restaurant")
    usages = relationship("CouponUsage", back_populates="coupon")


class CouponUsage(TimestampMixin, Base):
    __tablename__ = "coupon_usages"

    id = Column(Integer, primary_key=True, index=True)
    coupon_id = Column(Integer, ForeignKey("coupons.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)
    is_released = Column(Boolean, default=False, nullable=False)
    released_at = Column(DateTime, nullable=True)

    coupon = relationship("Coupon", back_populates="usages")
