from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import require_customer
from app.database import get_db
from app.models import CartItem, MenuItem, User
from app.schemas.cart import ApplyCouponIn, CartItemIn, CartItemUpdate, CartOut
from app.services.cart import add_item, build_cart_response, cart_totals, clear_cart, get_or_create_cart
from app.services.coupons import find_coupon, validate_coupon

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.get("", response_model=CartOut)
def get_cart(db: Session = Depends(get_db), user: User = Depends(require_customer)):
    return build_cart_response(db, get_or_create_cart(db, user))


@router.post("/items", response_model=CartOut, status_code=201)
def add_cart_item(data: CartItemIn, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    menu_item = db.get(MenuItem, data.menu_item_id)
    if menu_item is None or menu_item.is_deleted:
        raise HTTPException(404, "Menu item not found")
    cart = get_or_create_cart(db, user)
    add_item(db, cart, menu_item, data.quantity)
    db.commit()
    return build_cart_response(db, cart)


@router.put("/items/{item_id}", response_model=CartOut)
def update_cart_item(item_id: int, data: CartItemUpdate, db: Session = Depends(get_db),
                     user: User = Depends(require_customer)):
    cart = get_or_create_cart(db, user)
    ci = db.query(CartItem).filter(CartItem.id == item_id, CartItem.cart_id == cart.id).first()
    if ci is None:
        raise HTTPException(404, "Cart item not found")
    ci.quantity = data.quantity
    db.commit()
    return build_cart_response(db, cart)


@router.delete("/items/{item_id}", response_model=CartOut)
def remove_cart_item(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    cart = get_or_create_cart(db, user)
    ci = db.query(CartItem).filter(CartItem.id == item_id, CartItem.cart_id == cart.id).first()
    if ci is None:
        raise HTTPException(404, "Cart item not found")
    db.delete(ci)
    db.flush()
    db.refresh(cart)
    if not cart.items:
        cart.restaurant_id = None
        cart.coupon_id = None
    db.commit()
    return build_cart_response(db, cart)


@router.post("/apply-coupon", response_model=CartOut)
def apply_coupon(data: ApplyCouponIn, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    cart = get_or_create_cart(db, user)
    if not cart.items:
        raise HTTPException(400, "Cart is empty")
    coupon = find_coupon(db, data.code)
    if cart.coupon_id and coupon is not None and cart.coupon_id != coupon.id:
        raise HTTPException(400, "A coupon is already applied. Remove it first (only one coupon per order)")
    item_total, _ = cart_totals(cart)
    validate_coupon(db, coupon, user.id, cart.restaurant_id, item_total)
    cart.coupon_id = coupon.id
    db.commit()
    return build_cart_response(db, cart)


@router.delete("/coupon", response_model=CartOut)
def remove_coupon(db: Session = Depends(get_db), user: User = Depends(require_customer)):
    cart = get_or_create_cart(db, user)
    cart.coupon_id = None
    db.commit()
    return build_cart_response(db, cart)


@router.delete("", response_model=CartOut)
def clear(db: Session = Depends(get_db), user: User = Depends(require_customer)):
    cart = get_or_create_cart(db, user)
    clear_cart(cart, db)  # also removes the applied coupon
    db.commit()
    return build_cart_response(db, cart)
