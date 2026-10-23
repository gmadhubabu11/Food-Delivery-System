from datetime import date, datetime, time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing_extensions import Literal

from app.auth.deps import get_current_user, require_customer
from app.constants import Role
from app.database import get_db
from app.models import DeliveryPartner, MenuItem, Order, Restaurant, User
from app.schemas.cart import ReorderOut
from app.schemas.order import OrderCreate, OrderOut
from app.services import orders as order_service
from app.services.cart import add_item, build_cart_response, get_or_create_cart

router = APIRouter(prefix="/orders", tags=["Orders"])


def can_view(db: Session, order: Order, user: User) -> bool:
    if user.role == Role.ADMIN:
        return True
    if user.role == Role.CUSTOMER:
        return order.customer_id == user.id
    if user.role == Role.OWNER:
        return order.restaurant.owner_id == user.id
    if user.role == Role.PARTNER:
        p = db.query(DeliveryPartner).filter(DeliveryPartner.user_id == user.id).first()
        return p is not None and order.delivery_partner_id == p.id
    return False


def order_out(order: Order, user: User) -> OrderOut:
    out = OrderOut.model_validate(order)
    if user.role != Role.CUSTOMER:  # only the customer may see the delivery OTP
        out.delivery_otp = None
    return out


@router.post("", response_model=OrderOut, status_code=201)
def place_order(data: OrderCreate, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    return order_out(order_service.place_order(db, user, data), user)


@router.get("", response_model=List[OrderOut])
def list_orders(
    status: Optional[str] = None,
    restaurant_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    sort: Literal["asc", "desc"] = "desc",
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Order)
    if user.role == Role.CUSTOMER:
        q = q.filter(Order.customer_id == user.id)
    elif user.role == Role.OWNER:
        q = q.join(Restaurant, Restaurant.id == Order.restaurant_id).filter(Restaurant.owner_id == user.id)
    elif user.role == Role.PARTNER:
        p = db.query(DeliveryPartner).filter(DeliveryPartner.user_id == user.id).first()
        q = q.filter(Order.delivery_partner_id == (p.id if p else -1))
    if status:
        q = q.filter(Order.status == status)
    if restaurant_id:
        q = q.filter(Order.restaurant_id == restaurant_id)
    if from_date:
        q = q.filter(Order.placed_at >= datetime.combine(from_date, time.min))
    if to_date:
        q = q.filter(Order.placed_at <= datetime.combine(to_date, time.max))
    q = q.order_by(Order.placed_at.asc() if sort == "asc" else Order.placed_at.desc(), Order.id.desc())
    return [order_out(o, user) for o in q.offset(skip).limit(limit).all()]


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    if not can_view(db, order, user):
        raise HTTPException(403, "You do not have access to this order")
    return order_out(order, user)


@router.put("/{order_id}/cancel", response_model=OrderOut)
def cancel_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    order = db.get(Order, order_id)
    if order is None or order.customer_id != user.id:
        raise HTTPException(404, "Order not found")
    return order_out(order_service.cancel_order(db, order, user), user)


@router.post("/{order_id}/reorder", response_model=ReorderOut)
def reorder(order_id: int, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    order = db.get(Order, order_id)
    if order is None or order.customer_id != user.id:
        raise HTTPException(404, "Order not found")
    cart = get_or_create_cart(db, user)
    skipped = []
    for oi in order.items:
        mi = db.get(MenuItem, oi.menu_item_id)
        if mi is None or mi.is_deleted or not mi.is_available:
            skipped.append(oi.item_name)
            continue
        add_item(db, cart, mi, min(oi.quantity, 10))
    cart.coupon_id = None  # old coupon is never re-applied
    db.commit()
    return ReorderOut(cart=build_cart_response(db, cart), skipped_items=skipped)
