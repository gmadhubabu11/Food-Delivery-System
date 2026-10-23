from datetime import timedelta

from tests.conftest import add_coupon, auth, place_order
from app.utils.clock import now


def test_percentage_capped_and_case_insensitive(client, db, world):
    add_coupon(db, world["admin"], "BIG", discount_value=50, max_discount=100)  # 50% of 600 = 300 -> cap 100
    h = auth(world["cust"])
    client.post("/cart/items", json={"menu_item_id": world["i1"].id, "quantity": 2}, headers=h)
    r = client.post("/cart/apply-coupon", json={"code": "big"}, headers=h)
    assert r.status_code == 200
    assert r.json()["discount"] == 100
    assert r.json()["item_total_after_discount"] == 500


def test_min_order_message(client, db, world):
    add_coupon(db, world["admin"], "MIN500", min_order_value=500)
    h = auth(world["cust"])
    client.post("/cart/items", json={"menu_item_id": world["i1"].id, "quantity": 1}, headers=h)
    r = client.post("/cart/apply-coupon", json={"code": "MIN500"}, headers=h)
    assert r.status_code == 400
    assert r.json()["detail"] == "Minimum order value is ₹500"


def test_expired_coupon(client, db, world):
    add_coupon(db, world["admin"], "OLD", valid_from=now() - timedelta(days=3), valid_to=now() - timedelta(days=1))
    h = auth(world["cust"])
    client.post("/cart/items", json={"menu_item_id": world["i1"].id, "quantity": 1}, headers=h)
    r = client.post("/cart/apply-coupon", json={"code": "OLD"}, headers=h)
    assert r.status_code == 400 and r.json()["detail"] == "This coupon has expired"


def test_flat_discount_never_exceeds_item_total(client, db, world):
    add_coupon(db, world["admin"], "HUGE", discount_type="Flat", discount_value=5000, min_order_value=0)
    h = auth(world["cust"])
    client.post("/cart/items", json={"menu_item_id": world["i2"].id, "quantity": 3}, headers=h)  # 150
    r = client.post("/cart/apply-coupon", json={"code": "HUGE"}, headers=h)
    assert r.json()["discount"] == 150


def test_per_user_limit_and_release_on_cancel(client, db, world):
    add_coupon(db, world["admin"], "ONCE", per_user_limit=1)
    r = place_order(client, world, coupon="ONCE")
    assert r.status_code == 201
    h = auth(world["cust"])
    client.post("/cart/items", json={"menu_item_id": world["i1"].id}, headers=h)
    r2 = client.post("/cart/apply-coupon", json={"code": "ONCE"}, headers=h)
    assert r2.status_code == 400  # per-user limit reached
    # cancelling releases the usage
    client.put(f"/orders/{r.json()['id']}/cancel", headers=h)
    r3 = client.post("/cart/apply-coupon", json={"code": "ONCE"}, headers=h)
    assert r3.status_code == 200


def test_total_usage_limit(client, db, world):
    add_coupon(db, world["admin"], "LIM1", total_usage_limit=1, per_user_limit=5)
    assert place_order(client, world, coupon="LIM1").status_code == 201
    h = auth(world["cust"])
    client.post("/cart/items", json={"menu_item_id": world["i1"].id}, headers=h)
    r = client.post("/cart/apply-coupon", json={"code": "LIM1"}, headers=h)
    assert r.status_code == 400 and "usage limit" in r.json()["detail"]


def test_restaurant_coupon_wrong_restaurant(client, db, world):
    add_coupon(db, world["admin"], "OTHER", restaurant_id=world["rest"].id + 99)
    h = auth(world["cust"])
    client.post("/cart/items", json={"menu_item_id": world["i1"].id}, headers=h)
    r = client.post("/cart/apply-coupon", json={"code": "OTHER"}, headers=h)
    assert r.status_code == 400
