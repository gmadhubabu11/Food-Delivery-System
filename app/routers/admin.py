from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.deps import require_admin
from app.constants import Role
from app.database import get_db
from app.models import AdminNotification, DeliveryPartner, Order, User
from app.schemas.auth import ActiveStatusIn, UserOut

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", response_model=List[UserOut])
def list_users(
    role: Optional[str] = None, is_approved: Optional[bool] = None,
    skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db), _: User = Depends(require_admin),
):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    if is_approved is not None:
        q = q.filter(User.is_approved == is_approved)
    return q.order_by(User.id).offset(skip).limit(limit).all()


@router.put("/users/{user_id}/approve", response_model=UserOut)
def approve_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.role not in (Role.OWNER, Role.PARTNER):
        raise HTTPException(400, "Only restaurant owners and delivery partners need approval")
    user.is_approved = True
    if user.role == Role.PARTNER and user.partner_profile:
        user.partner_profile.is_approved = True
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}/status", response_model=UserOut)
def set_user_status(user_id: int, data: ActiveStatusIn, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        raise HTTPException(400, "You cannot change your own status")
    user.is_active = data.is_active
    db.commit()
    db.refresh(user)
    return user


@router.get("/notifications")
def notifications(unread_only: bool = False, skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                  db: Session = Depends(get_db), _: User = Depends(require_admin)):
    q = db.query(AdminNotification)
    if unread_only:
        q = q.filter(AdminNotification.is_read.is_(False))
    rows = q.order_by(AdminNotification.id.desc()).offset(skip).limit(limit).all()
    return [{"id": n.id, "kind": n.kind, "message": n.message, "order_id": n.order_id,
             "is_read": n.is_read, "created_at": n.created_at} for n in rows]


@router.put("/notifications/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    n = db.get(AdminNotification, notification_id)
    if n is None:
        raise HTTPException(404, "Notification not found")
    n.is_read = True
    db.commit()
    return {"detail": "Marked as read"}


@router.put("/orders/{order_id}/unlock-delivery")
def unlock_delivery(order_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Admin can unlock a delivery locked after 3 wrong OTP attempts."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    order.otp_locked = False
    order.otp_attempts = 0
    db.commit()
    return {"detail": "Delivery unlocked"}
