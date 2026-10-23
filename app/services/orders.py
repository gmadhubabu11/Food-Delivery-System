import random

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import OrderStatus, PaymentMethod, PaymentStatus
from app.models import (
    Address, Cart, Coupon, CouponUsage, MenuItem, Order, OrderItem, OrderStatusHistory, Restaurant, User,
)
from app.schemas.order import OrderCreate
from app.services import events
from app.services.billing import calculate_bill
from app.services.cart import cart_totals, clear_cart
from app.services.coupons import release_usage, validate_coupon
from app.utils.clock import is_restaurant_open, now
from app.utils.geo import haversine_km
from app.utils.money import D, fmt, q


def actor(user: User) -> str:
    return f"{user.role}:{user.id}"


def change_status(db: Session, order: Order, new_status: str, changed_by: str, note: str = None):
    """Single place that changes status and always writes the history row."""
    old = order.status
    order.status = new_status
    db.add(OrderStatusHistory(order_id=order.id, old_status=old, new_status=new_status,
                              changed_by=changed_by, note=note))
    db.flush()


def release_order_resources(db: Session, order: Order):
    """Cancelled/Rejected: refund online payments and release the coupon usage."""
    if order.payment_method == PaymentMethod.ONLINE and order.payment_status == PaymentStatus.PAID:
        order.payment_status = PaymentStatus.REFUNDED
    release_usage(db, order.id)


def generate_order_number(db: Session) -> str:
    prefix = f"ORD-{now().strftime('%Y%m%d')}-"
    last = db.query(func.max(Order.order_number)).filter(Order.order_number.like(prefix + "%")).scalar()
    seq = int(last.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{seq:04d}"


def generate_otp() -> str:
    return f"{random.SystemRandom().randint(0, 9999):04d}"


def reject_order(db: Session, order: Order, reason: str, changed_by: str, message: str = None):
    order.rejection_reason = reason
    change_status(db, order, OrderStatus.REJECTED, changed_by, reason)
    release_order_resources(db, order)
    db.commit()
    events.publish_order_update(order, message=message or f"Order rejected: {reason}")
    events.notify_customer(order, message or f"Your order {order.order_number} was rejected: {reason}")


def cancel_order(db: Session, order: Order, user: User):
    if order.status != OrderStatus.PLACED:
        raise HTTPException(400, "Order can be cancelled only while it is in Placed status")
    change_status(db, order, OrderStatus.CANCELLED, actor(user), "Cancelled by customer")
    release_order_resources(db, order)
    db.commit()
    events.publish_order_update(order, message="Order cancelled")
    return order


def place_order(db: Session, customer: User, data: OrderCreate) -> Order:
    """Everything below runs in ONE transaction; any failure rolls back everything."""
    try:
        cart = db.query(Cart).filter(Cart.customer_id == customer.id).with_for_update().first()
        if cart is None or not cart.items:
            raise HTTPException(400, "Cart is empty")
        restaurant = db.get(Restaurant, cart.restaurant_id)
        if restaurant is None or not is_restaurant_open(restaurant):
            raise HTTPException(400, "Restaurant is currently closed")
        address = db.query(Address).filter(
            Address.id == data.address_id, Address.customer_id == customer.id, Address.is_deleted.is_(False)
        ).first()
        if address is None:
            raise HTTPException(404, "Address not found")

        distance = round(haversine_km(restaurant.latitude, restaurant.longitude,
                                      address.latitude, address.longitude), 2)
        if distance > restaurant.delivery_radius_km:
            raise HTTPException(400, "Delivery address is outside the restaurant's delivery radius")

        for ci in cart.items:
            mi = ci.menu_item
            if mi.is_deleted or not mi.is_available:
                raise HTTPException(400, f"'{mi.name}' is no longer available. Remove it from the cart")

        item_total, packaging = cart_totals(cart)
        if item_total < D(restaurant.min_order_value):
            raise HTTPException(400, f"Minimum order value is {fmt(restaurant.min_order_value)}")

        # re-validate coupon (lock row so usage limits are race-safe)
        coupon, discount = None, D(0)
        if cart.coupon_id:
            coupon = db.query(Coupon).filter(Coupon.id == cart.coupon_id).with_for_update().first()
            discount = validate_coupon(db, coupon, customer.id, restaurant.id, item_total)

        bill = calculate_bill(item_total, discount, packaging, distance, data.tip_amount)
        online = data.payment_method == PaymentMethod.ONLINE
        order = Order(
            order_number=generate_order_number(db),
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            address_id=address.id,
            coupon_code=coupon.code if coupon else None,
            payment_method=data.payment_method,
            payment_status=PaymentStatus.PAID if online else PaymentStatus.PENDING,  # online = mock
            status=OrderStatus.PLACED,
            distance_km=distance,
            delivery_otp=generate_otp(),
            placed_at=now(),
            **bill,
        )
        db.add(order)
        db.flush()

        for ci in cart.items:
            mi: MenuItem = ci.menu_item
            db.add(OrderItem(
                order_id=order.id, menu_item_id=mi.id, item_name=mi.name, price=mi.price,
                quantity=ci.quantity, packaging_charge=mi.packaging_charge,
                line_total=q(D(mi.price) * ci.quantity),
            ))
        db.add(OrderStatusHistory(order_id=order.id, old_status=None, new_status=OrderStatus.PLACED,
                                  changed_by=actor(customer), note="Order placed"))
        if coupon:
            db.add(CouponUsage(coupon_id=coupon.id, customer_id=customer.id, order_id=order.id))
        clear_cart(cart, db)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Could not place the order due to a conflict. Please retry")
    except Exception:
        db.rollback()
        raise HTTPException(500, "Could not place the order. Nothing was saved")

    db.refresh(order)
    events.notify_new_order(order)
    events.publish_order_update(order)
    return order
