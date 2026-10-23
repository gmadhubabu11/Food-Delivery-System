from datetime import date, datetime, time, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.deps import get_approved_partner, get_partner_profile
from app.constants import (
    MAX_OTP_ATTEMPTS, PARTNER_BASE_EARNING, PARTNER_PER_KM_EARNING, OfferStatus, OrderStatus, PaymentMethod,
    PaymentStatus,
)
from app.database import get_db
from app.models import DeliveryOffer, DeliveryPartner, Order
from app.schemas.delivery import AvailabilityIn, LocationIn, OfferOut, PartnerOut
from app.schemas.order import OrderOut, OTPIn
from app.services import assignment, events
from app.services import orders as order_service
from app.utils.clock import now
from app.utils.money import D, q

router = APIRouter(tags=["Delivery Partner"])


def partner_out(p: DeliveryPartner) -> PartnerOut:
    return PartnerOut(
        id=p.id, user_id=p.user_id, vehicle_type=p.vehicle_type, vehicle_number=p.vehicle_number,
        is_online=p.is_online, current_latitude=p.current_latitude, current_longitude=p.current_longitude,
        last_location_at=p.last_location_at, is_approved=p.is_approved,
    )


def save_location(db: Session, partner: DeliveryPartner, lat: float, lon: float):
    """Used by PUT /partners/me/location and by the /ws/partner socket."""
    partner.current_latitude = lat
    partner.current_longitude = lon
    partner.last_location_at = now()
    db.commit()
    active = db.query(Order).filter(
        Order.delivery_partner_id == partner.id,
        Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY,
                          OrderStatus.PICKED_UP, OrderStatus.OUT_FOR_DELIVERY]),
    ).all()
    for order in active:
        events.publish_order_update(order, event="location_update")


@router.put("/partners/me/availability", response_model=PartnerOut)
def set_availability(data: AvailabilityIn, db: Session = Depends(get_db),
                     partner: DeliveryPartner = Depends(get_approved_partner)):
    if not data.is_online and assignment.partner_has_active_delivery(db, partner.id):
        raise HTTPException(409, "Finish your active delivery before going offline")
    partner.is_online = data.is_online
    db.commit()
    db.refresh(partner)
    return partner_out(partner)


@router.put("/partners/me/location", response_model=PartnerOut)
def update_location(data: LocationIn, db: Session = Depends(get_db),
                    partner: DeliveryPartner = Depends(get_approved_partner)):
    save_location(db, partner, data.latitude, data.longitude)
    db.refresh(partner)
    return partner_out(partner)


@router.get("/partners/me/offers", response_model=List[OfferOut])
def my_offers(db: Session = Depends(get_db), partner: DeliveryPartner = Depends(get_approved_partner)):
    offers = db.query(DeliveryOffer).filter(
        DeliveryOffer.partner_id == partner.id, DeliveryOffer.status == OfferStatus.PENDING,
        DeliveryOffer.expires_at > now(),
    ).order_by(DeliveryOffer.id.desc()).all()
    return [OfferOut(**events.offer_payload(o)) for o in offers]


@router.put("/offers/{offer_id}/accept", response_model=OrderOut)
def accept_offer(offer_id: int, db: Session = Depends(get_db), partner: DeliveryPartner = Depends(get_approved_partner)):
    if not partner.is_online:
        raise HTTPException(409, "Go online to accept offers")
    from app.routers.orders import order_out

    order = assignment.accept_offer(db, offer_id, partner)
    return order_out(order, partner.user)


@router.put("/offers/{offer_id}/decline")
def decline_offer(offer_id: int, db: Session = Depends(get_db), partner: DeliveryPartner = Depends(get_approved_partner)):
    assignment.decline_offer(db, offer_id, partner)
    return {"detail": "Offer declined"}


def _assigned_order(db: Session, order_id: int, partner: DeliveryPartner) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    if order.delivery_partner_id != partner.id:
        raise HTTPException(403, "This order is not assigned to you")
    return order


@router.put("/orders/{order_id}/pickup", response_model=OrderOut)
def pickup(order_id: int, db: Session = Depends(get_db), partner: DeliveryPartner = Depends(get_approved_partner)):
    from app.routers.orders import order_out

    order = _assigned_order(db, order_id, partner)
    if order.status != OrderStatus.READY:
        raise HTTPException(409, f"Order is not ready for pickup (current status: {order.status})")
    order.picked_up_at = now()
    order_service.change_status(db, order, OrderStatus.PICKED_UP, order_service.actor(partner.user))
    db.commit()
    events.publish_order_update(order, message="Partner picked up your order")
    return order_out(order, partner.user)


@router.put("/orders/{order_id}/out-for-delivery", response_model=OrderOut)
def out_for_delivery(order_id: int, db: Session = Depends(get_db),
                     partner: DeliveryPartner = Depends(get_approved_partner)):
    from app.routers.orders import order_out

    order = _assigned_order(db, order_id, partner)
    if order.status != OrderStatus.PICKED_UP:
        raise HTTPException(409, f"Order must be Picked Up first (current status: {order.status})")
    order_service.change_status(db, order, OrderStatus.OUT_FOR_DELIVERY, order_service.actor(partner.user))
    db.commit()
    events.publish_order_update(order, message="Your order is out for delivery")
    return order_out(order, partner.user)


@router.put("/orders/{order_id}/deliver", response_model=OrderOut)
def deliver(order_id: int, data: OTPIn, db: Session = Depends(get_db),
            partner: DeliveryPartner = Depends(get_approved_partner)):
    from app.routers.orders import order_out

    order = _assigned_order(db, order_id, partner)
    if order.status != OrderStatus.OUT_FOR_DELIVERY:
        raise HTTPException(409, f"Order must be Out for Delivery (current status: {order.status})")
    if order.otp_locked:
        raise HTTPException(403, "Delivery is locked after too many wrong OTP attempts. Contact Admin")
    if data.otp != order.delivery_otp:
        order.otp_attempts += 1
        left = MAX_OTP_ATTEMPTS - order.otp_attempts
        locked_now = left <= 0
        if locked_now:
            order.otp_locked = True
        db.commit()
        if locked_now:
            events.notify_admin(db, "delivery_locked",
                                f"Delivery of order {order.order_number} locked after {MAX_OTP_ATTEMPTS} wrong OTP attempts",
                                order.id)
            raise HTTPException(400, "Wrong OTP. Delivery is now locked and Admin has been notified")
        raise HTTPException(400, f"Wrong OTP. {left} attempt(s) left")

    order.delivered_at = now()
    if order.payment_method == PaymentMethod.COD:
        order.payment_status = PaymentStatus.PAID
    # coupons never reduce partner earnings
    order.partner_earning = q(D(PARTNER_BASE_EARNING) + D(PARTNER_PER_KM_EARNING) * D(order.distance_km)
                              + D(order.tip_amount))
    order_service.change_status(db, order, OrderStatus.DELIVERED, order_service.actor(partner.user))
    db.commit()
    events.publish_order_update(order, message="Order delivered. Enjoy your meal!")
    events.notify_customer(order, f"Order {order.order_number} delivered")
    return order_out(order, partner.user)


@router.get("/partners/me/earnings")
def earnings(
    from_date: Optional[date] = None, to_date: Optional[date] = None,
    db: Session = Depends(get_db), partner: DeliveryPartner = Depends(get_partner_profile),
):
    today = now().date()
    to_date = to_date or today
    from_date = from_date or (to_date - timedelta(days=6))
    if from_date > to_date:
        raise HTTPException(400, "from_date must be on or before to_date")

    def summary(start: date, end: date):
        row = db.query(func.count(Order.id), func.coalesce(func.sum(Order.partner_earning), 0)).filter(
            Order.delivery_partner_id == partner.id, Order.status == OrderStatus.DELIVERED,
            Order.delivered_at >= datetime.combine(start, time.min),
            Order.delivered_at <= datetime.combine(end, time.max),
        ).one()
        return {"deliveries": row[0], "earnings": float(row[1])}

    return {
        "today": {"date": today, **summary(today, today)},
        "range": {"from_date": from_date, "to_date": to_date, **summary(from_date, to_date)},
    }
