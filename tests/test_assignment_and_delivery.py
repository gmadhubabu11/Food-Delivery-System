from datetime import timedelta

from tests.conftest import auth, make_partner, place_order
from app.models import DeliveryOffer, Order
from app.services import assignment
from app.utils.clock import now


def _accept(client, w, oid):
    r = client.put(f"/orders/{oid}/accept", json={"estimated_preparation_minutes": 10}, headers=auth(w["owner"]))
    assert r.status_code == 200, r.text


def test_nearest_partner_gets_offer_first(client, db, world):
    far_u, far = make_partner(db, "far@t.com", 17.4800, 78.4000)   # ~3.3 km
    near_u, near = make_partner(db, "near@t.com", 17.4510, 78.3910)  # ~0.2 km
    out_u, out = make_partner(db, "out@t.com", 17.6000, 78.6000)   # >5 km: never offered
    db.commit()
    oid = place_order(client, world).json()["id"]
    _accept(client, world, oid)
    offers = db.query(DeliveryOffer).filter(DeliveryOffer.order_id == oid).all()
    assert len(offers) == 1 and offers[0].partner_id == near.id
    assert client.get("/partners/me/offers", headers=auth(near_u)).json()[0]["order_id"] == oid
    assert client.get("/partners/me/offers", headers=auth(far_u)).json() == []


def test_decline_moves_to_next_nearest_and_skips_decliner(client, db, world):
    u1, p1 = make_partner(db, "p1@t.com", 17.4510, 78.3910)
    u2, p2 = make_partner(db, "p2@t.com", 17.4600, 78.3950)
    db.commit()
    oid = place_order(client, world).json()["id"]
    _accept(client, world, oid)
    offer1 = db.query(DeliveryOffer).filter_by(order_id=oid, partner_id=p1.id).one()
    assert client.put(f"/offers/{offer1.id}/decline", headers=auth(u1)).status_code == 200
    db.expire_all()
    assert db.query(DeliveryOffer).filter_by(order_id=oid, partner_id=p2.id, status="Pending").count() == 1
    # decliner is never offered this order again
    assert p1.id not in [c.id for c in assignment.find_candidates(db, db.get(Order, oid))]


def test_offer_timeout_goes_to_next_partner(client, db, world):
    u1, p1 = make_partner(db, "t1@t.com", 17.4510, 78.3910)
    u2, p2 = make_partner(db, "t2@t.com", 17.4600, 78.3950)
    db.commit()
    oid = place_order(client, world).json()["id"]
    _accept(client, world, oid)
    offer1 = db.query(DeliveryOffer).filter_by(order_id=oid, partner_id=p1.id).one()
    offer1.expires_at = now() - timedelta(seconds=1)  # simulate 30s passing
    db.commit()
    assert assignment.expire_offers(db) == 1
    db.expire_all()
    assert db.get(DeliveryOffer, offer1.id).status == "Expired"
    assert db.query(DeliveryOffer).filter_by(order_id=oid, partner_id=p2.id, status="Pending").count() == 1
    # expired offers cannot be accepted
    assert client.put(f"/offers/{offer1.id}/accept", headers=auth(u1)).status_code == 409


def test_only_one_partner_can_win_and_one_active_delivery(client, db, world):
    u1, p1 = make_partner(db, "w1@t.com", 17.4510, 78.3910)
    db.commit()
    oid = place_order(client, world).json()["id"]
    _accept(client, world, oid)
    offer = db.query(DeliveryOffer).filter_by(order_id=oid).one()
    assert client.put(f"/offers/{offer.id}/accept", headers=auth(u1)).status_code == 200
    assert client.put(f"/offers/{offer.id}/accept", headers=auth(u1)).status_code == 409
    # busy partner is not a candidate for a second order
    oid2 = place_order(client, world).json()["id"]
    _accept(client, world, oid2)
    assert db.query(DeliveryOffer).filter_by(order_id=oid2).count() == 0


def _to_out_for_delivery(client, db, w):
    u, p = make_partner(db, "d@t.com", 17.4510, 78.3910)
    db.commit()
    oid = place_order(client, w, tip=20).json()["id"]
    _accept(client, w, oid)
    offer = db.query(DeliveryOffer).filter_by(order_id=oid).one()
    client.put(f"/offers/{offer.id}/accept", headers=auth(u))
    # pickup before ready is rejected
    assert client.put(f"/orders/{oid}/pickup", headers=auth(u)).status_code == 409
    client.put(f"/orders/{oid}/preparing", headers=auth(w["owner"]))
    client.put(f"/orders/{oid}/ready", headers=auth(w["owner"]))
    assert client.put(f"/orders/{oid}/pickup", headers=auth(u)).status_code == 200
    assert client.put(f"/orders/{oid}/out-for-delivery", headers=auth(u)).status_code == 200
    return u, oid


def test_delivery_otp_success_and_earnings(client, db, world):
    u, oid = _to_out_for_delivery(client, db, world)
    otp = db.get(Order, oid).delivery_otp
    r = client.put(f"/orders/{oid}/deliver", json={"otp": otp}, headers=auth(u))
    assert r.status_code == 200 and r.json()["status"] == "Delivered"
    assert r.json()["payment_status"] == "Paid"  # COD paid on delivery
    db.expire_all()
    order = db.get(Order, oid)
    assert float(order.partner_earning) == round(25 + 6 * order.distance_km + 20, 2)


def test_wrong_otp_locks_after_three_attempts(client, db, world):
    u, oid = _to_out_for_delivery(client, db, world)
    real = db.get(Order, oid).delivery_otp
    wrong = "0000" if real != "0000" else "1111"
    assert client.put(f"/orders/{oid}/deliver", json={"otp": wrong}, headers=auth(u)).status_code == 400
    assert client.put(f"/orders/{oid}/deliver", json={"otp": wrong}, headers=auth(u)).status_code == 400
    third = client.put(f"/orders/{oid}/deliver", json={"otp": wrong}, headers=auth(u))
    assert third.status_code == 400 and "locked" in third.json()["detail"]
    # even the right OTP is refused now
    assert client.put(f"/orders/{oid}/deliver", json={"otp": real}, headers=auth(u)).status_code == 403
    admin_notes = client.get("/admin/notifications", headers=auth(world["admin"])).json()
    assert any(n["kind"] == "delivery_locked" for n in admin_notes)


def test_invalid_otp_format_is_422(client, db, world):
    u, oid = _to_out_for_delivery(client, db, world)
    assert client.put(f"/orders/{oid}/deliver", json={"otp": "12"}, headers=auth(u)).status_code == 422
