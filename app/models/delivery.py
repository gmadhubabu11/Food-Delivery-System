from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import TimestampMixin


class DeliveryPartner(TimestampMixin, Base):
    __tablename__ = "delivery_partners"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    vehicle_type = Column(String(20), nullable=False)  # Bike | Scooter | Bicycle
    vehicle_number = Column(String(20), unique=True, nullable=False)
    is_online = Column(Boolean, default=False, nullable=False)
    current_latitude = Column(Float(53), nullable=True)
    current_longitude = Column(Float(53), nullable=True)
    last_location_at = Column(DateTime, nullable=True)
    is_approved = Column(Boolean, default=False, nullable=False)
    average_rating = Column(Float, default=0, nullable=False)

    user = relationship("User", back_populates="partner_profile")
    deliveries = relationship("Order", back_populates="partner")
    offers = relationship("DeliveryOffer", back_populates="partner")


class DeliveryOffer(TimestampMixin, Base):
    __tablename__ = "delivery_offers"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    partner_id = Column(Integer, ForeignKey("delivery_partners.id"), nullable=False, index=True)
    status = Column(String(10), nullable=False, default="Pending", index=True)
    offered_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    order = relationship("Order", back_populates="offers")
    partner = relationship("DeliveryPartner", back_populates="offers")


class AdminNotification(TimestampMixin, Base):
    __tablename__ = "admin_notifications"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(50), nullable=False)
    message = Column(String(255), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
