"""Tests run on a throw-away SQLite file. (The app itself never uses create_all; Alembic owns the schema.)"""
import os
import tempfile
from datetime import time, timedelta

os.environ["SCHEDULER_ENABLED"] = "false"
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.auth.security import create_access_token, hash_password  # noqa: E402
from app.constants import Role  # noqa: E402
from app.database import Base, get_db  # noqa: E402
import app.models as m  # noqa: E402
from app.main import app  # noqa: E402
from app.utils.clock import now  # noqa: E402

engine = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False})
TestingSession = sessionmaker(bind=engine, autoflush=True, autocommit=False)


def _override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = TestingSession()
    yield s
    s.close()


@pytest.fixture()
def client(db):
    return TestClient(app)


def make_user(db, role, email, approved=True, name=None):
    u = m.User(name=name or email.split("@")[0], email=email, phone="9999999999", role=role,
               password_hash=hash_password("secret1"), is_active=True, is_approved=approved)
    db.add(u)
    db.flush()
    return u


def make_partner(db, email, lat, lon, online=True):
    u = make_user(db, Role.PARTNER, email)
    p = m.DeliveryPartner(user_id=u.id, vehicle_type="Bike", vehicle_number=email.upper()[:15], is_approved=True,
                          is_online=online, current_latitude=lat, current_longitude=lon, last_location_at=now())
    db.add(p)
    db.flush()
    return u, p


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture()
def world(db):
    """Admin, owner, customer, one restaurant at (17.45, 78.39) with 2 items, customer address ~1.5 km away."""
    admin = make_user(db, Role.ADMIN, "admin@t.com")
    owner = make_user(db, Role.OWNER, "owner@t.com")
    cust = make_user(db, Role.CUSTOMER, "cust@t.com")
    rest = m.Restaurant(owner_id=owner.id, name="Test Biryani", cuisine_type="Biryani", address="x",
                        latitude=17.45, longitude=78.39, opening_time=time(0, 0, 0), closing_time=time(23, 59, 59),
                        delivery_radius_km=5, min_order_value=100, avg_preparation_minutes=20)
    db.add(rest)
    db.flush()
    cat = m.MenuCategory(restaurant_id=rest.id, name="Main")
    db.add(cat)
    db.flush()
    i1 = m.MenuItem(restaurant_id=rest.id, category_id=cat.id, name="Biryani", price=300, packaging_charge=10)
    i2 = m.MenuItem(restaurant_id=rest.id, category_id=cat.id, name="Raita", price=50, packaging_charge=5)
    addr = m.Address(customer_id=cust.id, label="Home", address_line="Home addr", city="Hyd", pincode="500081",
                     latitude=17.46, longitude=78.40, is_default=True)
    db.add_all([i1, i2, addr])
    db.commit()
    return {"admin": admin, "owner": owner, "cust": cust, "rest": rest, "i1": i1, "i2": i2, "addr": addr}


def add_coupon(db, admin, code="SAVE20", **kw):
    data = dict(description="t", discount_type="Percentage", discount_value=20, max_discount=100, min_order_value=100,
                restaurant_id=None, valid_from=now() - timedelta(days=1), valid_to=now() + timedelta(days=1),
                total_usage_limit=None, per_user_limit=1, first_order_only=False, created_by=admin.id, is_active=True)
    data.update(kw)
    c = m.Coupon(code=code, **data)
    db.add(c)
    db.commit()
    return c


def place_order(client, w, payment="COD", tip=0, coupon=None, qty=1):
    h = auth(w["cust"])
    r = client.post("/cart/items", json={"menu_item_id": w["i1"].id, "quantity": qty}, headers=h)
    assert r.status_code == 201, r.text
    if coupon:
        r = client.post("/cart/apply-coupon", json={"code": coupon}, headers=h)
        assert r.status_code == 200, r.text
    r = client.post("/orders", json={"address_id": w["addr"].id, "payment_method": payment, "tip_amount": tip}, headers=h)
    return r
