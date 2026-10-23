"""APScheduler jobs. Each job opens its own DB session and never lets an exception escape."""
import logging
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.constants import (
    AUTO_REJECT_AFTER_MINUTES, PARTNER_INACTIVE_MINUTES, OrderStatus,
)
from app.database import SessionLocal
from app.models import Coupon, DeliveryPartner, Order
from app.services import assignment
from app.services import orders as order_service
from app.utils.clock import now

log = logging.getLogger("scheduler")


def _run(fn):
    def wrapper():
        db = SessionLocal()
        try:
            fn(db)
        except Exception:
            db.rollback()
            log.exception("Job %s failed", fn.__name__)
        finally:
            db.close()

    wrapper.__name__ = fn.__name__
    return wrapper


def auto_reject_orders(db):
    """Placed for more than 5 minutes => rejected by System, refund + coupon release."""
    cutoff = now() - timedelta(minutes=AUTO_REJECT_AFTER_MINUTES)
    stale = db.query(Order).filter(Order.status == OrderStatus.PLACED, Order.placed_at <= cutoff).all()
    for order in stale:
        order_service.reject_order(
            db, order, "Restaurant did not respond", "System",
            message="Your order was automatically rejected because the restaurant did not respond",
        )


def expire_offers(db):
    assignment.expire_offers(db)


def retry_unassigned_orders(db):
    assignment.retry_unassigned(db)


def set_inactive_partners_offline(db):
    cutoff = now() - timedelta(minutes=PARTNER_INACTIVE_MINUTES)
    for p in db.query(DeliveryPartner).filter(DeliveryPartner.is_online.is_(True)).all():
        last_seen = p.last_location_at or p.updated_at
        if last_seen is None or last_seen <= cutoff:
            p.is_online = False
    db.commit()


def deactivate_expired_coupons(db):
    db.query(Coupon).filter(Coupon.is_active.is_(True), Coupon.valid_to < now()).update(
        {"is_active": False}, synchronize_session=False)
    db.commit()


def create_scheduler() -> BackgroundScheduler:
    s = BackgroundScheduler(timezone="UTC")
    opts = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 30}
    s.add_job(_run(auto_reject_orders), "interval", minutes=1, id="auto_reject", **opts)
    s.add_job(_run(expire_offers), "interval", seconds=10, id="offer_expiry", **opts)
    s.add_job(_run(retry_unassigned_orders), "interval", minutes=1, id="unassigned_orders", **opts)
    s.add_job(_run(set_inactive_partners_offline), "interval", minutes=5, id="inactive_partners", **opts)
    s.add_job(_run(deactivate_expired_coupons), "cron", hour=0, minute=5, id="coupon_expiry", **opts)
    return s
