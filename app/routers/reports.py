from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.deps import require_approved_owner, require_roles
from app.constants import Role, OrderStatus
from app.database import get_db
from app.models import DeliveryPartner, Order, OrderItem, Restaurant, User
from app.utils.clock import now

router = APIRouter(prefix="/reports", tags=["Reports"])

NOT_COUNTED = (OrderStatus.CANCELLED, OrderStatus.REJECTED)


def _range(from_date: Optional[date], to_date: Optional[date], days: int = 30):
    to_date = to_date or now().date()
    from_date = from_date or (to_date - timedelta(days=days - 1))
    if from_date > to_date:
        raise HTTPException(400, "from_date must be on or before to_date")
    return datetime.combine(from_date, time.min), datetime.combine(to_date, time.max), from_date, to_date


@router.get("/admin-dashboard")
def admin_dashboard(db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN))):
    start, end = datetime.combine(now().date(), time.min), datetime.combine(now().date(), time.max)
    today = db.query(Order).filter(Order.placed_at >= start, Order.placed_at <= end)
    total = today.count()
    delivered = today.filter(Order.status == OrderStatus.DELIVERED)
    cancelled = today.filter(Order.status == OrderStatus.CANCELLED).count()
    rejected = today.filter(Order.status == OrderStatus.REJECTED).count()
    revenue = delivered.with_entities(func.coalesce(func.sum(Order.grand_total), 0)).scalar()
    discount = today.filter(Order.status.notin_(NOT_COUNTED)).with_entities(
        func.coalesce(func.sum(Order.discount_amount), 0)).scalar()
    times = [(o.delivered_at - o.placed_at).total_seconds() / 60 for o in delivered.all() if o.delivered_at]
    online = db.query(DeliveryPartner).filter(DeliveryPartner.is_online.is_(True)).count()
    return {
        "date": now().date(),
        "total_orders": total,
        "delivered_orders": delivered.count(),
        "cancelled_orders": cancelled,
        "rejected_orders": rejected,
        "total_revenue": float(revenue),  # grand_total of delivered orders
        "total_discount_given": float(discount),  # orders that were not cancelled/rejected
        "online_partners": online,
        "average_delivery_minutes": round(sum(times) / len(times), 1) if times else 0,
    }


@router.get("/top-restaurants")
def top_restaurants(from_date: Optional[date] = None, to_date: Optional[date] = None,
                    db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN))):
    start, end, f, t = _range(from_date, to_date)
    rows = db.query(
        Restaurant.id, Restaurant.name, func.count(Order.id), func.coalesce(func.sum(Order.grand_total), 0)
    ).join(Order, Order.restaurant_id == Restaurant.id).filter(
        Order.status == OrderStatus.DELIVERED, Order.placed_at >= start, Order.placed_at <= end
    ).group_by(Restaurant.id, Restaurant.name).order_by(
        func.count(Order.id).desc(), func.sum(Order.grand_total).desc()).limit(10).all()
    return {"from_date": f, "to_date": t, "restaurants": [
        {"restaurant_id": r[0], "name": r[1], "orders": r[2], "revenue": float(r[3])} for r in rows]}


@router.get("/coupon-usage")
def coupon_usage(from_date: Optional[date] = None, to_date: Optional[date] = None,
                 db: Session = Depends(get_db), user: User = Depends(require_roles(Role.ADMIN, Role.OWNER))):
    start, end, f, t = _range(from_date, to_date)
    q = db.query(
        Order.coupon_code, func.count(Order.id), func.coalesce(func.sum(Order.discount_amount), 0),
        func.coalesce(func.sum(Order.grand_total), 0),
    ).filter(Order.coupon_code.isnot(None), Order.status.notin_(NOT_COUNTED),
             Order.placed_at >= start, Order.placed_at <= end)
    if user.role == Role.OWNER:
        q = q.join(Restaurant, Restaurant.id == Order.restaurant_id).filter(Restaurant.owner_id == user.id)
    rows = q.group_by(Order.coupon_code).order_by(func.count(Order.id).desc()).all()
    return {"from_date": f, "to_date": t, "coupons": [
        {"code": r[0], "times_used": r[1], "total_discount_given": float(r[2]), "revenue": float(r[3])} for r in rows]}


@router.get("/restaurant-sales")
def restaurant_sales(from_date: Optional[date] = None, to_date: Optional[date] = None,
                     restaurant_id: Optional[int] = None, db: Session = Depends(get_db),
                     owner: User = Depends(require_approved_owner)):
    start, end, f, t = _range(from_date, to_date)
    rids = [r.id for r in db.query(Restaurant.id).filter(Restaurant.owner_id == owner.id).all()]
    if restaurant_id is not None:
        if restaurant_id not in rids:
            raise HTTPException(403, "You can view reports only for your own restaurants")
        rids = [restaurant_id]
    base = db.query(Order).filter(Order.restaurant_id.in_(rids or [-1]), Order.status == OrderStatus.DELIVERED,
                                  Order.placed_at >= start, Order.placed_at <= end)
    daily = base.with_entities(
        func.date(Order.placed_at), func.count(Order.id), func.coalesce(func.sum(Order.grand_total), 0)
    ).group_by(func.date(Order.placed_at)).order_by(func.date(Order.placed_at)).all()
    best = db.query(OrderItem.item_name, func.sum(OrderItem.quantity), func.sum(OrderItem.line_total)).join(
        Order, Order.id == OrderItem.order_id).filter(
        Order.restaurant_id.in_(rids or [-1]), Order.status == OrderStatus.DELIVERED,
        Order.placed_at >= start, Order.placed_at <= end
    ).group_by(OrderItem.item_name).order_by(func.sum(OrderItem.quantity).desc()).limit(10).all()
    prep = [(o.ready_at - o.accepted_at).total_seconds() / 60 for o in base.all() if o.ready_at and o.accepted_at]
    return {
        "from_date": f, "to_date": t,
        "total_orders": sum(d[1] for d in daily),
        "total_sales": float(sum(d[2] for d in daily)),
        "daily_sales": [{"date": str(d[0]), "orders": d[1], "sales": float(d[2])} for d in daily],
        "best_selling_items": [{"item": b[0], "quantity": int(b[1]), "sales": float(b[2])} for b in best],
        "average_preparation_minutes": round(sum(prep) / len(prep), 1) if prep else 0,
    }


@router.get("/partner-summary")
def partner_summary(from_date: Optional[date] = None, to_date: Optional[date] = None,
                    db: Session = Depends(get_db), user: User = Depends(require_roles(Role.PARTNER))):
    start, end, f, t = _range(from_date, to_date, days=7)
    partner = db.query(DeliveryPartner).filter(DeliveryPartner.user_id == user.id).first()
    if partner is None:
        raise HTTPException(404, "Delivery partner profile not found")
    rows = db.query(
        func.date(Order.delivered_at), func.count(Order.id), func.coalesce(func.sum(Order.distance_km), 0),
        func.coalesce(func.sum(Order.partner_earning), 0),
    ).filter(Order.delivery_partner_id == partner.id, Order.status == OrderStatus.DELIVERED,
             Order.delivered_at >= start, Order.delivered_at <= end
             ).group_by(func.date(Order.delivered_at)).order_by(func.date(Order.delivered_at)).all()
    return {
        "from_date": f, "to_date": t,
        "deliveries_completed": sum(r[1] for r in rows),
        "total_distance_km": round(float(sum(r[2] for r in rows)), 2),
        "total_earnings": float(sum(r[3] for r in rows)),
        "by_day": [{"date": str(r[0]), "deliveries": r[1], "distance_km": round(float(r[2]), 2),
                    "earnings": float(r[3])} for r in rows],
    }
