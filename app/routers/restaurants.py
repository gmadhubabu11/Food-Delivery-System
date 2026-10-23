import math
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists
from sqlalchemy.orm import Session
from typing_extensions import Literal

from app.auth.deps import get_current_user, require_approved_owner, require_customer
from app.constants import Role
from app.database import get_db
from app.models import Coupon, MenuItem, Restaurant, User
from app.schemas.restaurant import (
    NearbyRestaurantOut, OpenStatusIn, RestaurantCreate, RestaurantOut, RestaurantUpdate,
)
from app.utils.clock import is_restaurant_open, now
from app.utils.geo import haversine_km, travel_minutes

router = APIRouter(prefix="/restaurants", tags=["Restaurants"])


def restaurant_out(r: Restaurant) -> RestaurantOut:
    out = RestaurantOut.model_validate(r)
    out.is_open = is_restaurant_open(r)
    return out


def get_owned_restaurant(db: Session, restaurant_id: int, owner: User) -> Restaurant:
    r = db.get(Restaurant, restaurant_id)
    if r is None:
        raise HTTPException(404, "Restaurant not found")
    if r.owner_id != owner.id:
        raise HTTPException(403, "You can manage only your own restaurants")
    return r


@router.post("", response_model=RestaurantOut, status_code=201)
def create_restaurant(data: RestaurantCreate, db: Session = Depends(get_db),
                      owner: User = Depends(require_approved_owner)):
    r = Restaurant(owner_id=owner.id, **data.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return restaurant_out(r)


@router.get("/me", response_model=List[RestaurantOut])
def my_restaurants(db: Session = Depends(get_db), owner: User = Depends(require_approved_owner)):
    rows = db.query(Restaurant).filter(Restaurant.owner_id == owner.id).order_by(Restaurant.id).all()
    return [restaurant_out(r) for r in rows]


@router.get("/nearby", response_model=List[NearbyRestaurantOut])
def nearby(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    name: Optional[str] = None,
    cuisine_type: Optional[str] = None,
    veg_only: bool = False,
    min_rating: Optional[float] = Query(None, ge=0, le=5),
    has_offers: bool = False,
    sort_by: Literal["distance", "rating", "estimated_delivery_minutes"] = "distance",
    order: Literal["asc", "desc"] = "asc",
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_customer),
):
    q = db.query(Restaurant).filter(Restaurant.is_active.is_(True), Restaurant.is_temporarily_closed.is_(False))
    if name:
        q = q.filter(Restaurant.name.ilike(f"%{name}%"))
    if cuisine_type:
        q = q.filter(Restaurant.cuisine_type.ilike(cuisine_type))
    if min_rating is not None:
        q = q.filter(Restaurant.average_rating >= min_rating)
    if veg_only:  # at least one (available, not deleted) veg item
        q = q.filter(exists().where(
            MenuItem.restaurant_id == Restaurant.id, MenuItem.is_veg.is_(True),
            MenuItem.is_deleted.is_(False), MenuItem.is_available.is_(True)))
    if has_offers:  # at least one active, currently valid coupon (restaurant-specific or platform-wide)
        n = now()
        q = q.filter(exists().where(
            Coupon.is_active.is_(True), Coupon.valid_from <= n, Coupon.valid_to >= n,
            (Coupon.restaurant_id == Restaurant.id) | (Coupon.restaurant_id.is_(None))))

    results = []
    for r in q.all():
        if not is_restaurant_open(r):
            continue
        d = haversine_km(latitude, longitude, r.latitude, r.longitude)
        if d > r.delivery_radius_km:
            continue
        out = NearbyRestaurantOut(
            **restaurant_out(r).model_dump(),
            distance_km=round(d, 2),
            estimated_delivery_minutes=int(math.ceil(r.avg_preparation_minutes + travel_minutes(d))),
        )
        results.append(out)

    key = {"distance": "distance_km", "rating": "average_rating",
           "estimated_delivery_minutes": "estimated_delivery_minutes"}[sort_by]
    results.sort(key=lambda x: getattr(x, key), reverse=(order == "desc"))
    return results[skip: skip + limit]


@router.get("/{restaurant_id}", response_model=RestaurantOut)
def get_restaurant(restaurant_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.get(Restaurant, restaurant_id)
    if r is None or (not r.is_active and user.role not in (Role.ADMIN,) and r.owner_id != user.id):
        raise HTTPException(404, "Restaurant not found")
    return restaurant_out(r)


@router.put("/{restaurant_id}", response_model=RestaurantOut)
def update_restaurant(restaurant_id: int, data: RestaurantUpdate, db: Session = Depends(get_db),
                      owner: User = Depends(require_approved_owner)):
    r = get_owned_restaurant(db, restaurant_id, owner)
    changes = data.model_dump(exclude_unset=True)
    opening = changes.get("opening_time", r.opening_time)
    closing = changes.get("closing_time", r.closing_time)
    if opening >= closing:
        raise HTTPException(422, "opening_time must be before closing_time")
    for k, v in changes.items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return restaurant_out(r)


@router.put("/{restaurant_id}/open-status", response_model=RestaurantOut)
def set_open_status(restaurant_id: int, data: OpenStatusIn, db: Session = Depends(get_db),
                    owner: User = Depends(require_approved_owner)):
    r = get_owned_restaurant(db, restaurant_id, owner)
    r.is_temporarily_closed = data.is_temporarily_closed
    db.commit()
    db.refresh(r)
    return restaurant_out(r)
