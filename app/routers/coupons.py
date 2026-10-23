from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing_extensions import Literal

from app.auth.deps import get_current_user, require_customer, require_roles
from app.constants import Role
from app.database import get_db
from app.models import Cart, Coupon, Restaurant, User
from app.schemas.coupon import AvailableCouponOut, CouponCreate, CouponOut, CouponUpdate
from app.services.cart import cart_totals
from app.services.coupons import find_coupon, validate_coupon
from app.utils.clock import now

router = APIRouter(prefix="/coupons", tags=["Coupons"])
staff = require_roles(Role.ADMIN, Role.OWNER)


def _approved_staff(user: User = Depends(staff)) -> User:
    if user.role == Role.OWNER and not user.is_approved:
        raise HTTPException(403, "Your account is pending admin approval")
    return user


def _can_manage(db: Session, coupon: Coupon, user: User) -> bool:
    if user.role == Role.ADMIN:
        return True
    if coupon.restaurant_id is None:
        return False  # platform-wide coupons belong to admin
    r = db.get(Restaurant, coupon.restaurant_id)
    return r is not None and r.owner_id == user.id


def _get_manageable(db: Session, coupon_id: int, user: User) -> Coupon:
    c = db.get(Coupon, coupon_id)
    if c is None:
        raise HTTPException(404, "Coupon not found")
    if not _can_manage(db, c, user):
        raise HTTPException(403, "You can manage only your own restaurants' coupons")
    return c


@router.post("", response_model=CouponOut, status_code=201)
def create_coupon(data: CouponCreate, db: Session = Depends(get_db), user: User = Depends(_approved_staff)):
    if user.role == Role.OWNER:
        if data.restaurant_id is None:
            raise HTTPException(403, "Restaurant owners can create coupons only for their own restaurants")
        r = db.get(Restaurant, data.restaurant_id)
        if r is None or r.owner_id != user.id:
            raise HTTPException(403, "You can create coupons only for your own restaurants")
    elif data.restaurant_id is not None and db.get(Restaurant, data.restaurant_id) is None:
        raise HTTPException(404, "Restaurant not found")
    code = data.code.strip().upper()
    if find_coupon(db, code):
        raise HTTPException(409, "Coupon code already exists")
    coupon = Coupon(**data.model_dump(exclude={"code"}), code=code, created_by=user.id)
    db.add(coupon)
    db.commit()
    db.refresh(coupon)
    return coupon


@router.get("", response_model=List[CouponOut])
def list_coupons(
    restaurant_id: Optional[int] = None, is_active: Optional[bool] = None,
    discount_type: Optional[Literal["Percentage", "Flat"]] = None,
    skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db), user: User = Depends(_approved_staff),
):
    q = db.query(Coupon)
    if user.role == Role.OWNER:
        ids = [r.id for r in db.query(Restaurant.id).filter(Restaurant.owner_id == user.id).all()]
        q = q.filter(Coupon.restaurant_id.in_(ids)) if ids else q.filter(Coupon.id == -1)
    if restaurant_id is not None:
        q = q.filter(Coupon.restaurant_id == restaurant_id)
    if is_active is not None:
        q = q.filter(Coupon.is_active == is_active)
    if discount_type:
        q = q.filter(Coupon.discount_type == discount_type)
    return q.order_by(Coupon.id.desc()).offset(skip).limit(limit).all()


@router.get("/available", response_model=List[AvailableCouponOut])
def available_coupons(db: Session = Depends(get_db), user: User = Depends(require_customer)):
    """Coupons the customer can use right now for the restaurant in their cart."""
    cart = db.query(Cart).filter(Cart.customer_id == user.id).first()
    if cart is None or not cart.items:
        return []
    item_total, _ = cart_totals(cart)
    n = now()
    candidates = db.query(Coupon).filter(
        Coupon.is_active.is_(True), Coupon.valid_from <= n, Coupon.valid_to >= n,
        or_(Coupon.restaurant_id.is_(None), Coupon.restaurant_id == cart.restaurant_id),
    ).all()
    result = []
    for c in candidates:
        try:
            discount = validate_coupon(db, c, user.id, cart.restaurant_id, item_total)
        except HTTPException:
            continue
        result.append(AvailableCouponOut(
            code=c.code, description=c.description, discount_type=c.discount_type,
            discount_value=c.discount_value, max_discount=c.max_discount, min_order_value=c.min_order_value,
            restaurant_id=c.restaurant_id, valid_to=c.valid_to, discount=discount,
        ))
    return sorted(result, key=lambda x: -x.discount)


@router.put("/{coupon_id}", response_model=CouponOut)
def update_coupon(coupon_id: int, data: CouponUpdate, db: Session = Depends(get_db),
                  user: User = Depends(_approved_staff)):
    c = _get_manageable(db, coupon_id, user)
    changes = data.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(c, k, v)
    if c.valid_to <= c.valid_from:
        raise HTTPException(422, "valid_to must be after valid_from")
    if c.discount_type == "Percentage" and not (1 <= float(c.discount_value) <= 100):
        raise HTTPException(422, "Percentage coupons must have discount_value between 1 and 100")
    db.commit()
    db.refresh(c)
    return c


@router.put("/{coupon_id}/deactivate", response_model=CouponOut)
def deactivate_coupon(coupon_id: int, db: Session = Depends(get_db), user: User = Depends(_approved_staff)):
    c = _get_manageable(db, coupon_id, user)
    c.is_active = False
    db.commit()
    db.refresh(c)
    return c
