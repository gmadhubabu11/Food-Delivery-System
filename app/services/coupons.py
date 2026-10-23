from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants import DiscountType, OrderStatus
from app.models import Coupon, CouponUsage, Order
from app.utils.clock import now
from app.utils.money import D, fmt, q


def find_coupon(db: Session, code: str, lock: bool = False) -> Optional[Coupon]:
    query = db.query(Coupon).filter(func.upper(Coupon.code) == code.strip().upper())
    if lock:
        query = query.with_for_update()
    return query.first()


def active_usage_count(db: Session, coupon_id: int, customer_id: Optional[int] = None) -> int:
    q_ = db.query(func.count(CouponUsage.id)).filter(
        CouponUsage.coupon_id == coupon_id, CouponUsage.is_released.is_(False)
    )
    if customer_id is not None:
        q_ = q_.filter(CouponUsage.customer_id == customer_id)
    return q_.scalar() or 0


def compute_discount(coupon: Coupon, item_total) -> Decimal:
    item_total = D(item_total)
    if coupon.discount_type == DiscountType.PERCENTAGE:
        discount = item_total * D(coupon.discount_value) / D(100)
        if coupon.max_discount is not None:
            discount = min(discount, D(coupon.max_discount))
    else:
        discount = D(coupon.discount_value)
    return q(min(discount, item_total))  # never more than the item total


def validate_coupon(db: Session, coupon: Optional[Coupon], customer_id: int, restaurant_id: int, item_total) -> Decimal:
    """Raises HTTPException(400, reason) if unusable, else returns the discount."""
    if coupon is None:
        raise HTTPException(400, "Invalid coupon code")
    if not coupon.is_active:
        raise HTTPException(400, "This coupon is not active")
    at = now()
    if at < coupon.valid_from:
        raise HTTPException(400, "This coupon is not valid yet")
    if at > coupon.valid_to:
        raise HTTPException(400, "This coupon has expired")
    if coupon.restaurant_id is not None and coupon.restaurant_id != restaurant_id:
        raise HTTPException(400, "This coupon is not valid for this restaurant")
    if D(item_total) < D(coupon.min_order_value):
        raise HTTPException(400, f"Minimum order value is {fmt(coupon.min_order_value)}")
    if coupon.total_usage_limit is not None and active_usage_count(db, coupon.id) >= coupon.total_usage_limit:
        raise HTTPException(400, "This coupon has reached its usage limit")
    if coupon.per_user_limit is not None and active_usage_count(db, coupon.id, customer_id) >= coupon.per_user_limit:
        raise HTTPException(400, "You have already used this coupon the maximum number of times")
    if coupon.first_order_only:
        delivered = db.query(func.count(Order.id)).filter(
            Order.customer_id == customer_id, Order.status == OrderStatus.DELIVERED
        ).scalar() or 0
        if delivered > 0:
            raise HTTPException(400, "This coupon is valid only on your first order")
    return compute_discount(coupon, item_total)


def release_usage(db: Session, order_id: int):
    usage = db.query(CouponUsage).filter(
        CouponUsage.order_id == order_id, CouponUsage.is_released.is_(False)
    ).first()
    if usage:
        usage.is_released = True
        usage.released_at = now()
