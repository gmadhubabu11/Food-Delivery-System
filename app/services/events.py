"""Builds payloads and pushes them to WebSocket rooms. Always call AFTER db.commit()."""
import math
from typing import Optional

from sqlalchemy.orm import Session

from app.constants import (
    ASSIGNABLE_STATUSES, PARTNER_BASE_EARNING, PARTNER_PER_KM_EARNING, OrderStatus,
)
from app.models import AdminNotification, DeliveryOffer, DeliveryPartner, Order
from app.utils.clock import now
from app.utils.geo import haversine_km, travel_minutes
from app.websockets.manager import manager


def _remaining(order: Order):
    """Returns (distance_remaining_km, eta_minutes) or (None, None) if not applicable."""
    if order.status in (OrderStatus.PLACED, OrderStatus.DELIVERED, OrderStatus.REJECTED, OrderStatus.CANCELLED):
        return None, None
    rest, addr, partner = order.restaurant, order.address, order.partner
    has_loc = partner is not None and partner.current_latitude is not None
    if has_loc and order.status in (OrderStatus.PICKED_UP, OrderStatus.OUT_FOR_DELIVERY):
        dist = haversine_km(partner.current_latitude, partner.current_longitude, addr.latitude, addr.longitude)
        eta = travel_minutes(dist)
    else:
        prep_left = 0.0
        if order.status in (OrderStatus.ACCEPTED, OrderStatus.PREPARING) and order.accepted_at:
            elapsed = (now() - order.accepted_at).total_seconds() / 60
            prep_left = max(0.0, (order.estimated_preparation_minutes or 0) - elapsed)
        to_rest = (
            haversine_km(partner.current_latitude, partner.current_longitude, rest.latitude, rest.longitude)
            if has_loc else 0.0
        )
        dist = to_rest + order.distance_km
        eta = max(travel_minutes(to_rest), prep_left) + travel_minutes(order.distance_km)
    return round(dist, 2), int(math.ceil(eta))


def tracking_payload(order: Order, event: str = "order_update", message: Optional[str] = None) -> dict:
    p = order.partner
    partner = None
    if p is not None:
        partner = {
            "name": p.user.name if p.user else None,
            "vehicle_type": p.vehicle_type,
            "vehicle_number": p.vehicle_number,
            "latitude": p.current_latitude,
            "longitude": p.current_longitude,
            "last_location_at": p.last_location_at,
        }
    dist, eta = _remaining(order)
    return {
        "type": event,
        "order_id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "message": message,
        "partner": partner,
        "distance_remaining_km": dist,
        "eta_minutes": eta,
        "timestamp": now(),
    }


def publish_order_update(order: Order, event: str = "order_update", message: Optional[str] = None):
    manager.publish(f"order:{order.id}", tracking_payload(order, event, message))


def notify_customer(order: Order, message: str, event: str = "notification"):
    manager.publish(
        f"customer:{order.customer_id}",
        {"type": event, "order_id": order.id, "order_number": order.order_number,
         "status": order.status, "message": message, "timestamp": now()},
    )


def notify_new_order(order: Order):
    from app.schemas.order import OrderOut

    data = OrderOut.model_validate(order).model_dump(exclude={"delivery_otp"})
    manager.publish(
        f"restaurant:{order.restaurant.owner_id}",
        {"type": "new_order", "order": data, "customer_name": order.customer.name},
    )


def offer_payload(offer: DeliveryOffer) -> dict:
    order, partner = offer.order, offer.partner
    pickup = None
    if partner.current_latitude is not None:
        pickup = round(haversine_km(partner.current_latitude, partner.current_longitude,
                                    order.restaurant.latitude, order.restaurant.longitude), 2)
    earnings = PARTNER_BASE_EARNING + PARTNER_PER_KM_EARNING * order.distance_km + float(order.tip_amount)
    return {
        "offer_id": offer.id,
        "order_id": order.id,
        "order_number": order.order_number,
        "status": offer.status,
        "restaurant_name": order.restaurant.name,
        "pickup_distance_km": pickup,
        "delivery_distance_km": round(order.distance_km, 2),
        "expected_earnings": round(earnings, 2),
        "seconds_left": max(0, int((offer.expires_at - now()).total_seconds())),
        "expires_at": offer.expires_at,
    }


def notify_offer(offer: DeliveryOffer):
    manager.publish(f"partner:{offer.partner.user_id}", {"type": "delivery_offer", **offer_payload(offer)})


def notify_admin(db: Session, kind: str, message: str, order_id: Optional[int] = None):
    """Persist an admin notification (commits) and push it live."""
    db.add(AdminNotification(kind=kind, message=message, order_id=order_id))
    db.commit()
    manager.publish("admin", {"type": kind, "message": message, "order_id": order_id, "timestamp": now()})
