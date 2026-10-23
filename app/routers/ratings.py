from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_customer
from app.constants import OrderStatus
from app.database import get_db
from app.models import DeliveryPartner, Order, Rating, Restaurant, User
from app.schemas.rating import RatingCreate, RatingOut

router = APIRouter(tags=["Ratings"])


@router.post("/orders/{order_id}/rating", response_model=RatingOut, status_code=201)
def rate_order(order_id: int, data: RatingCreate, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    order = db.get(Order, order_id)
    if order is None or order.customer_id != user.id:
        raise HTTPException(404, "Order not found")
    if order.status != OrderStatus.DELIVERED:
        raise HTTPException(400, "You can rate an order only after it is Delivered")
    if db.query(Rating).filter(Rating.order_id == order.id).first():
        raise HTTPException(409, "This order has already been rated")

    rating = Rating(
        order_id=order.id, customer_id=user.id, restaurant_id=order.restaurant_id,
        partner_id=order.delivery_partner_id, restaurant_rating=data.restaurant_rating,
        partner_rating=data.partner_rating, comment=data.comment,
    )
    db.add(rating)
    db.flush()
    avg = db.query(func.avg(Rating.restaurant_rating)).filter(Rating.restaurant_id == order.restaurant_id).scalar()
    db.get(Restaurant, order.restaurant_id).average_rating = round(float(avg or 0), 2)
    if order.delivery_partner_id:
        pavg = db.query(func.avg(Rating.partner_rating)).filter(Rating.partner_id == order.delivery_partner_id).scalar()
        db.get(DeliveryPartner, order.delivery_partner_id).average_rating = round(float(pavg or 0), 2)
    db.commit()
    db.refresh(rating)
    return rating


@router.get("/restaurants/{restaurant_id}/ratings", response_model=List[RatingOut])
def restaurant_ratings(restaurant_id: int, skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100),
                       db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if db.get(Restaurant, restaurant_id) is None:
        raise HTTPException(404, "Restaurant not found")
    return db.query(Rating).filter(Rating.restaurant_id == restaurant_id).order_by(Rating.id.desc()).offset(skip).limit(limit).all()
