"""Creates the Admin account plus sample data. Run: python -m app.utils.seed  (idempotent)."""
from datetime import time, timedelta

from app.auth.security import hash_password
from app.config import settings
from app.constants import Role
from app.database import SessionLocal
from app.models import (
    Address, Coupon, DeliveryPartner, MenuCategory, MenuItem, Restaurant, User,
)
from app.utils.clock import now

PASSWORD = "Pass@123"


def _user(db, name, email, phone, role, password=PASSWORD, approved=True):
    u = db.query(User).filter(User.email == email).first()
    if u:
        return u
    u = User(name=name, email=email, phone=phone, role=role, password_hash=hash_password(password),
             is_active=True, is_approved=approved)
    db.add(u)
    db.flush()
    return u


def run():
    db = SessionLocal()
    try:
        admin = _user(db, "Platform Admin", settings.ADMIN_EMAIL, "9000000000", Role.ADMIN, settings.ADMIN_PASSWORD)
        owner = _user(db, "Ravi Owner", "owner@food.com", "9000000001", Role.OWNER)
        _user(db, "Pending Owner", "owner.pending@food.com", "9000000009", Role.OWNER, approved=False)
        customer = _user(db, "Anita Customer", "customer@food.com", "9000000002", Role.CUSTOMER)

        partners = [
            ("Partner One", "partner1@food.com", "9000000011", "Bike", "TS09AB1001", 17.4490, 78.3880),
            ("Partner Two", "partner2@food.com", "9000000012", "Scooter", "TS09AB1002", 17.4510, 78.3900),
            ("Partner Three", "partner3@food.com", "9000000013", "Bicycle", "TS09AB1003", 17.4600, 78.4000),
        ]
        for name, email, phone, vtype, vno, lat, lon in partners:
            u = _user(db, name, email, phone, Role.PARTNER)
            if not db.query(DeliveryPartner).filter(DeliveryPartner.user_id == u.id).first():
                db.add(DeliveryPartner(user_id=u.id, vehicle_type=vtype, vehicle_number=vno, is_approved=True,
                                       is_online=True, current_latitude=lat, current_longitude=lon,
                                       last_location_at=now()))

        if not db.query(Address).filter(Address.customer_id == customer.id).first():
            db.add(Address(customer_id=customer.id, label="Home", address_line="Madhapur, Hyderabad",
                           city="Hyderabad", pincode="500081", latitude=17.4486, longitude=78.3908, is_default=True))
            db.add(Address(customer_id=customer.id, label="Work", address_line="Gachibowli, Hyderabad",
                           city="Hyderabad", pincode="500032", latitude=17.4400, longitude=78.3800))

        if not db.query(Restaurant).filter(Restaurant.owner_id == owner.id).first():
            data = [
                ("Paradise Biryani", "Biryani", "Madhapur Main Road", 17.4500, 78.3850, 25,
                 {"Biryani": [("Chicken Dum Biryani", 299, False, 0), ("Veg Biryani", 199, True, 10),
                              ("Mutton Biryani", 399, False, 15)],
                  "Starters": [("Chicken 65", 220, False, 10), ("Paneer Tikka", 210, True, 10)]}),
                ("Spice Garden", "South Indian", "Kondapur", 17.4420, 78.3920, 15,
                 {"Tiffins": [("Masala Dosa", 99, True, 5), ("Idli (3 pcs)", 60, True, 5), ("Pongal", 80, True, 5)],
                  "Meals": [("South Indian Thali", 180, True, 10)]}),
                ("Pizza Hub", "Pizza", "Hitech City", 17.4560, 78.3990, 20,
                 {"Pizzas": [("Margherita", 249, True, 15), ("Pepperoni", 349, False, 15)],
                  "Sides": [("Garlic Bread", 129, True, 5)]}),
            ]
            for name, cuisine, addr, lat, lon, prep, menu in data:
                r = Restaurant(owner_id=owner.id, name=name, cuisine_type=cuisine, address=addr, latitude=lat,
                               longitude=lon, opening_time=time(0, 0, 0), closing_time=time(23, 59, 59),
                               delivery_radius_km=5, min_order_value=99, avg_preparation_minutes=prep)
                db.add(r)
                db.flush()
                for cat_name, items in menu.items():
                    cat = MenuCategory(restaurant_id=r.id, name=cat_name)
                    db.add(cat)
                    db.flush()
                    for iname, price, veg, pack in items:
                        db.add(MenuItem(restaurant_id=r.id, category_id=cat.id, name=iname, price=price,
                                        is_veg=veg, packaging_charge=10 if price >= 150 else 5,
                                        description=f"{iname} from {name}"))

        paradise = db.query(Restaurant).filter(Restaurant.name == "Paradise Biryani").first()
        coupons = [
            ("WELCOME50", "Flat Rs 50 off on your first order", "Flat", 50, None, 199, None, True, 1000, 1),
            ("BIRYANI20", "20% off (max Rs 100) at Paradise Biryani", "Percentage", 20, 100, 299,
             paradise.id if paradise else None, False, 500, 5),
            ("FLAT100", "Flat Rs 100 off on orders above Rs 599", "Flat", 100, None, 599, None, False, 500, 3),
            ("SAVE10", "10% off up to Rs 50", "Percentage", 10, 50, 149, None, False, None, 5),
        ]
        for code, desc, dtype, val, maxd, minv, rid, first, total, per in coupons:
            if not db.query(Coupon).filter(Coupon.code == code).first():
                db.add(Coupon(code=code, description=desc, discount_type=dtype, discount_value=val,
                              max_discount=maxd, min_order_value=minv, restaurant_id=rid,
                              valid_from=now() - timedelta(days=1), valid_to=now() + timedelta(days=90),
                              total_usage_limit=total, per_user_limit=per, first_order_only=first,
                              created_by=admin.id, is_active=True))
        db.commit()
        print("Seed complete.")
        print(f"Admin: {settings.ADMIN_EMAIL} / {settings.ADMIN_PASSWORD}")
        print(f"Others: owner@food.com, customer@food.com, partner1..3@food.com  (password {PASSWORD})")
    finally:
        db.close()


if __name__ == "__main__":
    run()
