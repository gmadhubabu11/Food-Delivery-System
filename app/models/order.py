from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.utils.clock import now


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(30), unique=True, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False, index=True)
    address_id = Column(Integer, ForeignKey("addresses.id"), nullable=False)
    delivery_partner_id = Column(Integer, ForeignKey("delivery_partners.id"), nullable=True, index=True)

    item_total = Column(Numeric(10, 2), nullable=False)
    coupon_code = Column(String(50), nullable=True)
    discount_amount = Column(Numeric(10, 2), default=0, nullable=False)
    packaging_charges = Column(Numeric(10, 2), default=0, nullable=False)
    delivery_fee = Column(Numeric(10, 2), nullable=False)
    platform_fee = Column(Numeric(10, 2), nullable=False)
    gst_amount = Column(Numeric(10, 2), nullable=False)
    tip_amount = Column(Numeric(10, 2), default=0, nullable=False)
    grand_total = Column(Numeric(10, 2), nullable=False)

    payment_method = Column(String(10), nullable=False)  # COD | Online
    payment_status = Column(String(10), nullable=False, default="Pending")
    status = Column(String(30), nullable=False, default="Placed", index=True)
    distance_km = Column(Float, nullable=False)
    delivery_otp = Column(String(4), nullable=False)

    rejection_reason = Column(String(255), nullable=True)
    estimated_preparation_minutes = Column(Integer, nullable=True)
    otp_attempts = Column(Integer, default=0, nullable=False)
    otp_locked = Column(Boolean, default=False, nullable=False)
    unassigned_alert_sent = Column(Boolean, default=False, nullable=False)
    partner_earning = Column(Numeric(10, 2), nullable=True)

    placed_at = Column(DateTime, default=now, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    ready_at = Column(DateTime, nullable=True)
    picked_up_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)

    customer = relationship("User", back_populates="orders")
    restaurant = relationship("Restaurant", back_populates="orders")
    address = relationship("Address")
    partner = relationship("DeliveryPartner", back_populates="deliveries")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    history = relationship(
        "OrderStatusHistory", back_populates="order", cascade="all, delete-orphan",
        order_by="OrderStatusHistory.id",
    )
    offers = relationship("DeliveryOffer", back_populates="order")
    rating = relationship("Rating", back_populates="order", uselist=False)


class OrderItem(TimestampMixin, Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=False)
    item_name = Column(String(150), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)  # price at the time of order
    quantity = Column(Integer, nullable=False)
    packaging_charge = Column(Numeric(10, 2), default=0, nullable=False)
    line_total = Column(Numeric(10, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    menu_item = relationship("MenuItem")


class OrderStatusHistory(TimestampMixin, Base):
    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    old_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=False)
    changed_by = Column(String(100), nullable=False)  # "System" or "<role>:<user_id>"
    note = Column(String(255), nullable=True)

    order = relationship("Order", back_populates="history")


class Rating(TimestampMixin, Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False, index=True)
    partner_id = Column(Integer, ForeignKey("delivery_partners.id"), nullable=True)
    restaurant_rating = Column(Integer, nullable=False)
    partner_rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)

    order = relationship("Order", back_populates="rating")
    customer = relationship("User")
