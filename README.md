# Food Delivery System (FastAPI)

Customers order from nearby restaurants, apply coupons, restaurants accept and prepare orders, and the nearest
delivery partner delivers with live tracking. JWT auth with 4 roles, Haversine location search, coupons, nearest
partner assignment with row locking, delivery OTP, WebSockets, APScheduler jobs, Alembic migrations and reports.

**Stack:** Python 3.9+, FastAPI, Pydantic v2, SQLAlchemy 2, MySQL (PyMySQL), Alembic, python-jose (JWT), Passlib (bcrypt), WebSockets, APScheduler, Uvicorn.

## 1. Setup

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then edit DATABASE_URL and JWT_SECRET_KEY
```

Create the database (MySQL 8):

```sql
CREATE DATABASE food_delivery CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### Alembic (tables are created ONLY by migrations - `create_all` is never used by the app)

```bash
alembic upgrade head                                   # create all tables
alembic current                                        # show current revision
alembic revision --autogenerate -m "describe change"   # after changing models
alembic downgrade -1                                   # roll back one revision
```

### Seed sample data (admin, users, restaurants, menus, partners, coupons)

```bash
python -m app.utils.seed
```

### Run

```bash
uvicorn app.main:app --reload
```

* Swagger UI: http://localhost:8000/docs  (use **Authorize** - username = email, password)
* WebSocket test page: http://localhost:8000/tracking-test
* Scheduled jobs start automatically with the app (set `SCHEDULER_ENABLED=false` to disable).

### Docker (bonus)

```bash
docker compose up --build      # MySQL + API; runs migrations and seed automatically
```

### Tests (bonus)

```bash
pytest -v      # uses a temporary SQLite file; covers assignment, offer timeout, OTP, coupons, cancellation
```

## 2. Test credentials (created by the seed script)

| Role | Email | Password |
|---|---|---|
| Admin | admin@food.com | Admin@123 |
| Restaurant Owner (approved) | owner@food.com | Pass@123 |
| Restaurant Owner (pending approval) | owner.pending@food.com | Pass@123 |
| Customer | customer@food.com | Pass@123 |
| Delivery Partner 1-3 (approved, online) | partner1@food.com, partner2@food.com, partner3@food.com | Pass@123 |

Admin accounts cannot be registered publicly; the admin is created by the seed script (`ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env`).

## 3. Sample locations used for testing (Hyderabad)

| What | Latitude | Longitude |
|---|---|---|
| Customer search point / Home address | 17.4486 | 78.3908 |
| Customer Work address | 17.4400 | 78.3800 |
| Paradise Biryani (Biryani) | 17.4500 | 78.3850 |
| Spice Garden (South Indian) | 17.4420 | 78.3920 |
| Pizza Hub (Pizza) | 17.4560 | 78.3990 |
| Partner One | 17.4490 | 78.3880 |
| Partner Two | 17.4510 | 78.3900 |
| Partner Three | 17.4600 | 78.4000 |

Seeded restaurants are open 00:00-23:59:59 so you can test at any hour (restaurant open = within opening/closing time and not temporarily closed).

## 4. Sample coupon codes

| Code | Rule |
|---|---|
| WELCOME50 | Flat Rs 50, min Rs 199, first order only (no previous Delivered order) |
| BIRYANI20 | 20% up to Rs 100, min Rs 299, only Paradise Biryani |
| FLAT100 | Flat Rs 100, min Rs 599, all restaurants |
| SAVE10 | 10% up to Rs 50, min Rs 149, all restaurants, 5 uses per user |

## 5. End-to-end test flow (Swagger)

1. Login as customer -> `GET /restaurants/nearby?latitude=17.4486&longitude=78.3908`
2. `GET /restaurants/{id}/menu` -> `POST /cart/items` -> `GET /coupons/available` -> `POST /cart/apply-coupon`
3. `GET /addresses` -> `POST /orders` (note `delivery_otp` in the response - only the customer sees it)
4. Login as owner -> `GET /restaurants/me/orders` -> `PUT /orders/{id}/accept` (`{"estimated_preparation_minutes": 15}`) -> `/preparing` -> `/ready`
5. Accepting starts assignment: login as the nearest partner -> `GET /partners/me/offers` -> `PUT /offers/{id}/accept` (30 s window)
6. Partner: `PUT /orders/{id}/pickup` -> `/out-for-delivery` -> `/deliver` with `{"otp": "<customer otp>"}`
7. Customer: `POST /orders/{id}/rating`
8. Admin: `GET /reports/admin-dashboard`

## 6. WebSocket testing

Endpoints (token is the JWT from `/auth/login`, sent as `?token=`):

| Endpoint | Who | Receives |
|---|---|---|
| `WS /ws/orders/{order_id}` | customer of the order, owner of its restaurant, assigned partner, admin | status changes, partner location, distance remaining, ETA |
| `WS /ws/restaurant` | restaurant owner | new orders (`type: new_order`) |
| `WS /ws/partner` | delivery partner | delivery offers (`type: delivery_offer`); partner can also **send** `{"type":"location","latitude":17.45,"longitude":78.39}` |
| `WS /ws/customer` (extra) | customer | notifications such as auto-rejected orders |
| `WS /ws/admin` (extra) | admin | alerts: unassigned order after 15 min, locked delivery |

Invalid/expired tokens, wrong role or an order you may not see -> an error message is sent and the connection is closed with code 1008.

**A. Postman:** New -> WebSocket -> `ws://localhost:8000/ws/orders/1?token=<access_token>` -> Connect. Then change the order status from Swagger and watch the message arrive instantly. For live location, connect `ws://localhost:8000/ws/partner?token=<partner_token>` in a second tab and send the location JSON every 5-10 s (or call `PUT /partners/me/location`).

**B. Browser console:**
```js
const ws = new WebSocket("ws://localhost:8000/ws/orders/1?token=<access_token>");
ws.onmessage = (e) => console.log("Update:", e.data);
```

**C. HTML test page:** open http://localhost:8000/tracking-test, paste the token, enter the order id, click Connect. Status, partner location, distance remaining and ETA update live.

## 7. API overview

Auth: `/auth/register|login|me`, `/auth/token` (form login for Swagger), `PUT /admin/users/{id}/approve`.
Restaurants/menu: `/restaurants`, `/restaurants/me`, `/restaurants/nearby`, `/restaurants/{id}/(menu|categories|menu-items|open-status|ratings)`, `/menu-items/{id}`.
Addresses, cart, coupons, orders, restaurant order handling, partners/offers/deliveries, ratings and reports exactly as listed in the assignment.
Extras: `GET /admin/users`, `PUT /admin/users/{id}/status`, `GET /admin/notifications`, `PUT /admin/orders/{id}/unlock-delivery`.

Pagination: `skip` and `limit` on all list APIs. Filtering/sorting: see the Level 14 parameters on `/restaurants/nearby`, `/orders`, `/coupons`.

## 8. Assumptions

1. **Timezone:** all datetimes are stored as naive local time using `TZ_OFFSET_MINUTES` (default 330 = IST). Opening hours, coupon validity and peak hours use the same clock.
2. **Roles / approval:** customers are approved at registration; owners and partners start unapproved. Unapproved partners cannot go online or accept offers; unapproved owners cannot create restaurants.
3. **Delivery partner registration** requires `vehicle_type` (Bike/Scooter/Bicycle) and `vehicle_number`.
4. **Login:** `POST /auth/login` takes JSON; `POST /auth/token` is the form variant used by Swagger's Authorize button. Inactive users get 403 on login.
5. **Cart item id:** `PUT/DELETE /cart/items/{item_id}` use the **cart item id** returned in the cart response.
6. **Coupons:** stored upper-case, matched case-insensitively. Admin coupons with no `restaurant_id` are platform-wide. Only one coupon per cart: remove the current one before applying another. A coupon that becomes invalid while in the cart is silently removed and a `coupon_message` explains why. Usage is counted only when an order is placed and released on cancel/reject/auto-reject.
7. **Bill:** delivery fee = Rs 20 up to 3 km + Rs 8 per extra km (rounded up); platform fee Rs 5; GST 5% of (item total - discount); amounts rounded half-up to 2 decimals. `distance_km` is rounded to 2 decimals.
8. **Surge pricing (bonus):** set `SURGE_PRICING_ENABLED=true` to multiply the delivery fee by 1.5 during 12-14 and 19-22 (off by default so bills are predictable while testing).
9. **Nearby search:** `has_offers` = at least one currently valid active coupon that is restaurant-specific or platform-wide; `veg_only` = at least one available, non-deleted veg item. `estimated_delivery_minutes` = avg prep minutes + travel time at 20 km/h (rounded up).
10. **Partner assignment:** offers go to one partner at a time. Eligible = approved, online, has a location, no active delivery, no other pending offer, within 5 km of the restaurant. Partners who declined an order are never re-offered it; partners whose earlier offer only expired are tried last.
11. **Partner earnings** = Rs 25 + Rs 6 x `distance_km` (restaurant -> customer) + tip, saved when delivered.
12. **OTP:** 3 wrong attempts lock the delivery (further attempts -> 403) and notify Admin; Admin can unlock with `PUT /admin/orders/{id}/unlock-delivery`.
13. **Status transitions** that break the forward-only flow return 409; cancelling after acceptance returns 400.
14. **Address / menu item delete** are soft deletes. Deleting a menu item also removes it from open carts.
15. **Reports:** "revenue" = grand total of Delivered orders; "total discount given" = discount on orders that were not cancelled/rejected; average delivery time = placed -> delivered minutes.
16. **Not implemented:** the bonus "scheduled orders" feature.
#   F o o d - D e l i v e r y - S y s t e m  
 