from tests.conftest import auth, make_user
from app.constants import Role


def test_register_login_me(client, db):
    r = client.post("/auth/register", json={"name": "Cu", "email": "A@B.com", "phone": "9876543210",
                                            "password": "secret1", "role": "customer"})
    assert r.status_code == 201 and r.json()["is_approved"] is True
    t = client.post("/auth/login", json={"email": "a@b.com", "password": "secret1"})
    assert t.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {t.json()['access_token']}"})
    assert me.json()["email"] == "a@b.com"


def test_admin_cannot_self_register_and_duplicates(client, db):
    body = {"name": "Ad", "email": "ad@b.com", "phone": "9876543210", "password": "secret1", "role": "admin"}
    assert client.post("/auth/register", json=body).status_code == 422
    ok = dict(body, role="customer")
    assert client.post("/auth/register", json=ok).status_code == 201
    assert client.post("/auth/register", json=ok).status_code == 409
    assert client.post("/auth/register", json=dict(ok, email="x@y.com", phone="123")).status_code == 422


def test_invalid_token_401_and_wrong_role_403(client, db, world):
    assert client.get("/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.get("/cart", headers=auth(world["owner"])).status_code == 403


def test_inactive_user_cannot_login(client, db):
    u = make_user(db, Role.CUSTOMER, "gone@t.com")
    u.is_active = False
    db.commit()
    assert client.post("/auth/login", json={"email": "gone@t.com", "password": "secret1"}).status_code == 403


def test_unapproved_owner_blocked_until_admin_approves(client, db, world):
    pending = make_user(db, Role.OWNER, "pend@t.com", approved=False)
    db.commit()
    body = {"name": "R", "cuisine_type": "Pizza", "address": "abc", "latitude": 17.4, "longitude": 78.3,
            "opening_time": "09:00:00", "closing_time": "22:00:00"}
    assert client.post("/restaurants", json=body, headers=auth(pending)).status_code == 403
    assert client.put(f"/admin/users/{pending.id}/approve", headers=auth(world["admin"])).status_code == 200
    assert client.post("/restaurants", json=body, headers=auth(pending)).status_code == 201
    body["opening_time"], body["closing_time"] = "22:00:00", "09:00:00"
    assert client.post("/restaurants", json=body, headers=auth(pending)).status_code == 422


def test_nearby_search_filters_and_distance(client, db, world):
    h = auth(world["cust"])
    r = client.get("/restaurants/nearby?latitude=17.4486&longitude=78.3908", headers=h)
    assert r.status_code == 200 and len(r.json()) == 1
    row = r.json()[0]
    assert row["distance_km"] < 1 and row["estimated_delivery_minutes"] >= 20
    far = client.get("/restaurants/nearby?latitude=18.5&longitude=79.5", headers=h)
    assert far.json() == []
    assert client.get("/restaurants/nearby?latitude=95&longitude=79", headers=h).status_code == 422
    assert client.get("/restaurants/nearby?latitude=17.4486&longitude=78.3908&cuisine_type=Pizza", headers=h).json() == []


def test_cart_rules(client, db, world):
    import app.models as m
    h = auth(world["cust"])
    assert client.post("/cart/items", json={"menu_item_id": world["i1"].id, "quantity": 11}, headers=h).status_code == 422
    client.post("/cart/items", json={"menu_item_id": world["i1"].id, "quantity": 2}, headers=h)
    r = client.post("/cart/items", json={"menu_item_id": world["i1"].id, "quantity": 3}, headers=h)
    assert r.json()["items"][0]["quantity"] == 5
    # unavailable item cannot be added
    world["i2"].is_available = False
    db.commit()
    assert client.post("/cart/items", json={"menu_item_id": world["i2"].id}, headers=h).status_code == 400
    # other restaurant => 409
    owner2 = make_user(db, Role.OWNER, "o2@t.com")
    from datetime import time
    r2 = m.Restaurant(owner_id=owner2.id, name="R2", cuisine_type="Pizza", address="a", latitude=17.45, longitude=78.39,
                      opening_time=time(0), closing_time=time(23, 59, 59))
    db.add(r2)
    db.flush()
    c2 = m.MenuCategory(restaurant_id=r2.id, name="c")
    db.add(c2)
    db.flush()
    it = m.MenuItem(restaurant_id=r2.id, category_id=c2.id, name="Pz", price=200)
    db.add(it)
    db.commit()
    r = client.post("/cart/items", json={"menu_item_id": it.id}, headers=h)
    assert r.status_code == 409
    assert r.json()["detail"] == "Your cart has items from another restaurant. Clear the cart to continue"
