from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Cart, User
from app.schemas.cart import CartItemOut, CartOut
from app.services.coupons import validate_coupon
from app.utils.money import D, q


def get_or_create_cart(db: Session, user: User) -> Cart:
    cart = db.query(Cart).filter(Cart.customer_id == user.id).first()
    if cart is None:
        cart = Cart(customer_id=user.id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


def cart_totals(cart: Cart):
    """Returns (item_total, packaging_total)."""
    item_total, packaging = Decimal("0"), Decimal("0")
    for ci in cart.items:
        item_total += D(ci.menu_item.price) * ci.quantity
        packaging += D(ci.menu_item.packaging_charge) * ci.quantity
    return q(item_total), q(packaging)


def clear_cart(cart: Cart, db: Session):
    for ci in list(cart.items):
        db.delete(ci)
    cart.restaurant_id = None
    cart.coupon_id = None


def build_cart_response(db: Session, cart: Cart) -> CartOut:
    """Builds the cart view; silently drops an applied coupon that is no longer valid."""
    db.refresh(cart)
    if not cart.items and (cart.restaurant_id or cart.coupon_id):
        cart.restaurant_id = None
        cart.coupon_id = None
        db.commit()
    item_total, _ = cart_totals(cart)
    discount, message, code = Decimal("0.00"), None, None
    if cart.coupon_id and cart.coupon is not None:
        try:
            discount = validate_coupon(db, cart.coupon, cart.customer_id, cart.restaurant_id, item_total)
            code = cart.coupon.code
        except HTTPException as exc:
            message = f"Coupon {cart.coupon.code} removed: {exc.detail}"
            cart.coupon_id = None
            db.commit()
    items = [
        CartItemOut(
            id=ci.id, menu_item_id=ci.menu_item_id, name=ci.menu_item.name, is_veg=ci.menu_item.is_veg,
            price=ci.menu_item.price, quantity=ci.quantity,
            line_total=q(D(ci.menu_item.price) * ci.quantity),
            is_available=ci.menu_item.is_available and not ci.menu_item.is_deleted,
        )
        for ci in sorted(cart.items, key=lambda x: x.id)
    ]
    return CartOut(
        cart_id=cart.id,
        restaurant_id=cart.restaurant_id,
        restaurant_name=cart.restaurant.name if cart.restaurant else None,
        items=items,
        item_total=item_total,
        coupon_code=code,
        discount=discount,
        item_total_after_discount=q(item_total - discount),
        coupon_message=message,
    )


def add_item(db: Session, cart: Cart, menu_item, quantity: int):
    """Shared by POST /cart/items and reorder. Raises HTTPException on rule violations."""
    from app.constants import MAX_ITEM_QUANTITY

    if menu_item.is_deleted or not menu_item.is_available:
        raise HTTPException(400, f"'{menu_item.name}' is currently unavailable")
    if not menu_item.restaurant.is_active:
        raise HTTPException(400, "Restaurant is not active")
    if cart.items and cart.restaurant_id != menu_item.restaurant_id:
        raise HTTPException(409, "Your cart has items from another restaurant. Clear the cart to continue")
    existing: Optional[object] = next((ci for ci in cart.items if ci.menu_item_id == menu_item.id), None)
    if existing:
        if existing.quantity + quantity > MAX_ITEM_QUANTITY:
            raise HTTPException(400, f"Quantity per item cannot exceed {MAX_ITEM_QUANTITY}")
        existing.quantity += quantity
    else:
        from app.models import CartItem

        db.add(CartItem(cart_id=cart.id, menu_item_id=menu_item.id, quantity=quantity))
    cart.restaurant_id = menu_item.restaurant_id
    db.flush()
    db.refresh(cart)
