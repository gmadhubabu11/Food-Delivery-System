from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.deps import require_approved_owner
from app.constants import OrderStatus
from app.database import get_db
from app.models import Order, Restaurant, User
from app.routers.orders import order_out
from app.schemas.order import AcceptIn, OrderOut, RejectIn
from app.services import assignment, events
from app.services import orders as order_service
from app.utils.clock import now

router = APIRouter(tags=["Restaurant Orders"])


def _owned_order(db: Session, order_id: int, owner: User) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    if order.restaurant.owner_id != owner.id:
        raise HTTPException(403, "Only the owner of the order's restaurant can do this")
    return order


def _require(order: Order, expected: str, action: str):
    if order.status != expected:
        raise HTTPException(409, f"Cannot {action}: order is {order.status}, expected {expected}")


@router.get("/restaurants/me/orders", response_model=List[OrderOut])
def restaurant_orders(
    status: Optional[str] = None, restaurant_id: Optional[int] = None,
    skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db), owner: User = Depends(require_approved_owner),
):
    q = db.query(Order).join(Restaurant, Restaurant.id == Order.restaurant_id).filter(Restaurant.owner_id == owner.id)
    if status:
        q = q.filter(Order.status == status)
    if restaurant_id:
        q = q.filter(Order.restaurant_id == restaurant_id)
    return [order_out(o, owner) for o in q.order_by(Order.id.desc()).offset(skip).limit(limit).all()]


@router.put("/orders/{order_id}/accept", response_model=OrderOut)
def accept(order_id: int, data: AcceptIn, db: Session = Depends(get_db), owner: User = Depends(require_approved_owner)):
    order = _owned_order(db, order_id, owner)
    _require(order, OrderStatus.PLACED, "accept")
    order.estimated_preparation_minutes = data.estimated_preparation_minutes
    order.accepted_at = now()
    order_service.change_status(db, order, OrderStatus.ACCEPTED, order_service.actor(owner))
    db.commit()
    events.publish_order_update(order, message="Restaurant accepted your order")
    events.notify_customer(order, f"Order {order.order_number} accepted. Preparing in ~{data.estimated_preparation_minutes} min")
    assignment.offer_next(db, order)  # start delivery partner assignment
    return order_out(order, owner)


@router.put("/orders/{order_id}/reject", response_model=OrderOut)
def reject(order_id: int, data: RejectIn, db: Session = Depends(get_db), owner: User = Depends(require_approved_owner)):
    order = _owned_order(db, order_id, owner)
    _require(order, OrderStatus.PLACED, "reject")
    order_service.reject_order(db, order, data.reason, order_service.actor(owner))
    return order_out(order, owner)


@router.put("/orders/{order_id}/preparing", response_model=OrderOut)
def preparing(order_id: int, db: Session = Depends(get_db), owner: User = Depends(require_approved_owner)):
    order = _owned_order(db, order_id, owner)
    _require(order, OrderStatus.ACCEPTED, "start preparing")
    order_service.change_status(db, order, OrderStatus.PREPARING, order_service.actor(owner))
    db.commit()
    events.publish_order_update(order, message="Your food is being prepared")
    return order_out(order, owner)


@router.put("/orders/{order_id}/ready", response_model=OrderOut)
def ready(order_id: int, db: Session = Depends(get_db), owner: User = Depends(require_approved_owner)):
    order = _owned_order(db, order_id, owner)
    _require(order, OrderStatus.PREPARING, "mark ready")
    order.ready_at = now()
    order_service.change_status(db, order, OrderStatus.READY, order_service.actor(owner))
    db.commit()
    events.publish_order_update(order, message="Your order is ready for pickup")
    return order_out(order, owner)
