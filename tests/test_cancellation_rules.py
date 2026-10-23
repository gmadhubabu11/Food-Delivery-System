from tests.conftest import auth, place_order
from app.models import Order


def test_cancel_while_placed_refunds_online(client, db, world):
    r = place_order(client, world, payment="Online")
    assert r.status_code == 201
    assert r.json()["payment_status"] == "Paid"
    oid = r.json()["id"]
    c = client.put(f"/orders/{oid}/cancel", headers=auth(world["cust"]))
    assert c.status_code == 200
    assert c.json()["status"] == "Cancelled"
    assert c.json()["payment_status"] == "Refunded"
    assert [h["new_status"] for h in c.json()["history"]] == ["Placed", "Cancelled"]


def test_cannot_cancel_after_accept(client, db, world):
    oid = place_order(client, world).json()["id"]
    a = client.put(f"/orders/{oid}/accept", json={"estimated_preparation_minutes": 15}, headers=auth(world["owner"]))
    assert a.status_code == 200
    c = client.put(f"/orders/{oid}/cancel", headers=auth(world["cust"]))
    assert c.status_code == 400


def test_reject_requires_reason_and_refunds(client, db, world):
    oid = place_order(client, world, payment="Online").json()["id"]
    h = auth(world["owner"])
    assert client.put(f"/orders/{oid}/reject", json={}, headers=h).status_code == 422
    r = client.put(f"/orders/{oid}/reject", json={"reason": "Out of stock"}, headers=h)
    assert r.status_code == 200 and r.json()["payment_status"] == "Refunded"


def test_otp_only_visible_to_customer(client, db, world):
    oid = place_order(client, world).json()["id"]
    assert len(client.get(f"/orders/{oid}", headers=auth(world["cust"])).json()["delivery_otp"]) == 4
    assert client.get(f"/orders/{oid}", headers=auth(world["owner"])).json()["delivery_otp"] is None


def test_bill_calculation(client, db, world):
    # 1 x 300, packaging 10, distance ~1.5km => delivery 20, platform 5, GST 5% of 300 = 15
    o = place_order(client, world, tip=10).json()
    assert o["item_total"] == 300 and o["packaging_charges"] == 10
    assert o["delivery_fee"] == 20 and o["platform_fee"] == 5 and o["gst_amount"] == 15
    assert o["grand_total"] == 300 + 10 + 20 + 5 + 15 + 10


def test_place_order_rules(client, db, world):
    h = auth(world["cust"])
    r = client.post("/orders", json={"address_id": world["addr"].id, "payment_method": "COD"}, headers=h)
    assert r.status_code == 400 and r.json()["detail"] == "Cart is empty"
    client.post("/cart/items", json={"menu_item_id": world["i2"].id}, headers=h)  # 50 < min 100
    r = client.post("/orders", json={"address_id": world["addr"].id, "payment_method": "COD"}, headers=h)
    assert r.status_code == 400 and "Minimum order value" in r.json()["detail"]
    assert db.query(Order).count() == 0
