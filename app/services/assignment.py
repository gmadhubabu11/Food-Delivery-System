"""Nearest-partner assignment, offer lifecycle and unassigned-order handling."""
from datetime import timedelta
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.constants import (
    ACTIVE_DELIVERY_STATUSES, ASSIGNABLE_STATUSES, OFFER_TTL_SECONDS, PARTNER_SEARCH_RADIUS_KM,
    UNASSIGNED_ALERT_AFTER_MINUTES, OfferStatus,
)
from app.models import DeliveryOffer, DeliveryPartner, Order
from app.services import events
from app.utils.clock import now
from app.utils.geo import haversine_km


def partner_has_active_delivery(db: Session, partner_id: int) -> bool:
    return db.query(Order.id).filter(
        Order.delivery_partner_id == partner_id, Order.status.in_(ACTIVE_DELIVERY_STATUSES)
    ).first() is not None


def find_candidates(db: Session, order: Order) -> List[DeliveryPartner]:
    """Approved + online + free + within 5 km of the restaurant, nearest first.
    Partners who DECLINED this order are always skipped; partners whose earlier offer merely
    EXPIRED are tried last. Partners holding another pending offer are skipped."""
    rest = order.restaurant
    declined = {o.partner_id for o in order.offers if o.status == OfferStatus.DECLINED}
    expired = {o.partner_id for o in order.offers if o.status == OfferStatus.EXPIRED}
    busy_offer = {
        r[0] for r in db.query(DeliveryOffer.partner_id).filter(
            DeliveryOffer.status == OfferStatus.PENDING, DeliveryOffer.expires_at > now()
        ).all()
    }
    partners = db.query(DeliveryPartner).filter(
        DeliveryPartner.is_approved.is_(True), DeliveryPartner.is_online.is_(True),
        DeliveryPartner.current_latitude.isnot(None), DeliveryPartner.current_longitude.isnot(None),
    ).all()
    ranked = []
    for p in partners:
        if p.id in declined or p.id in busy_offer or partner_has_active_delivery(db, p.id):
            continue
        d = haversine_km(rest.latitude, rest.longitude, p.current_latitude, p.current_longitude)
        if d <= PARTNER_SEARCH_RADIUS_KM:
            ranked.append((p.id in expired, d, p))
    ranked.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in ranked]


def offer_next(db: Session, order: Order) -> Optional[DeliveryOffer]:
    """Offer the order to the nearest eligible partner (one pending offer at a time)."""
    if order.delivery_partner_id is not None or order.status not in ASSIGNABLE_STATUSES:
        return None
    pending = db.query(DeliveryOffer).filter(
        DeliveryOffer.order_id == order.id, DeliveryOffer.status == OfferStatus.PENDING,
        DeliveryOffer.expires_at > now(),
    ).first()
    if pending:
        return pending
    candidates = find_candidates(db, order)
    if not candidates:
        return None
    offered_at = now()
    offer = DeliveryOffer(
        order_id=order.id, partner_id=candidates[0].id, status=OfferStatus.PENDING,
        offered_at=offered_at, expires_at=offered_at + timedelta(seconds=OFFER_TTL_SECONDS),
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    events.notify_offer(offer)
    return offer


def accept_offer(db: Session, offer_id: int, partner: DeliveryPartner) -> Order:
    """Row-locks the order so two partners can never both get it."""
    offer = db.query(DeliveryOffer).filter(DeliveryOffer.id == offer_id).first()
    if offer is None or offer.partner_id != partner.id:
        raise HTTPException(404, "Offer not found")
    order = db.query(Order).filter(Order.id == offer.order_id).with_for_update().first()
    db.query(DeliveryPartner).filter(DeliveryPartner.id == partner.id).with_for_update().first()
    db.refresh(offer)
    if offer.status != OfferStatus.PENDING:
        db.rollback()
        raise HTTPException(409, f"Offer is already {offer.status}")
    if offer.expires_at <= now():
        offer.status = OfferStatus.EXPIRED
        db.commit()
        raise HTTPException(409, "Offer has expired")
    if order.delivery_partner_id is not None:
        offer.status = OfferStatus.EXPIRED
        db.commit()
        raise HTTPException(409, "Order is already assigned to another partner")
    if order.status not in ASSIGNABLE_STATUSES:
        offer.status = OfferStatus.EXPIRED
        db.commit()
        raise HTTPException(409, "Order is no longer available for delivery")
    if partner_has_active_delivery(db, partner.id):
        db.rollback()
        raise HTTPException(409, "You already have an active delivery")

    offer.status = OfferStatus.ACCEPTED
    order.delivery_partner_id = partner.id
    for other in db.query(DeliveryOffer).filter(
        DeliveryOffer.order_id == order.id, DeliveryOffer.id != offer.id,
        DeliveryOffer.status == OfferStatus.PENDING,
    ).all():
        other.status = OfferStatus.EXPIRED
    db.commit()
    db.refresh(order)
    events.publish_order_update(order, message="Delivery partner assigned")
    events.notify_customer(order, f"{partner.user.name} will deliver your order")
    return order


def decline_offer(db: Session, offer_id: int, partner: DeliveryPartner):
    offer = db.query(DeliveryOffer).filter(DeliveryOffer.id == offer_id).first()
    if offer is None or offer.partner_id != partner.id:
        raise HTTPException(404, "Offer not found")
    if offer.status != OfferStatus.PENDING:
        raise HTTPException(409, f"Offer is already {offer.status}")
    offer.status = OfferStatus.DECLINED
    db.commit()
    db.refresh(offer)
    offer_next(db, offer.order)
    return offer


def expire_offers(db: Session) -> int:
    """Mark overdue pending offers Expired and move each order on to the next partner."""
    overdue = db.query(DeliveryOffer).filter(
        DeliveryOffer.status == OfferStatus.PENDING, DeliveryOffer.expires_at <= now()
    ).all()
    orders = {}
    for o in overdue:
        o.status = OfferStatus.EXPIRED
        orders[o.order_id] = o.order
    db.commit()
    for order in orders.values():
        offer_next(db, order)
    return len(overdue)


def retry_unassigned(db: Session) -> int:
    """Retry assignment for accepted orders without a partner; alert Admin after 15 minutes."""
    orders = db.query(Order).filter(
        Order.status.in_(ASSIGNABLE_STATUSES), Order.delivery_partner_id.is_(None)
    ).all()
    for order in orders:
        offer_next(db, order)
        waited = now() - (order.accepted_at or order.placed_at)
        if waited >= timedelta(minutes=UNASSIGNED_ALERT_AFTER_MINUTES) and not order.unassigned_alert_sent:
            order.unassigned_alert_sent = True
            db.commit()
            events.notify_admin(
                db, "order_unassigned",
                f"Order {order.order_number} has no delivery partner after {UNASSIGNED_ALERT_AFTER_MINUTES} minutes",
                order.id,
            )
    return len(orders)
