"""WebSocket endpoints. Auth: JWT in the ?token= query parameter; invalid token => connection closed."""
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.auth.deps import user_from_token
from app.constants import Role
from app.database import SessionLocal
from app.models import DeliveryPartner, Order, User
from app.services import events
from app.websockets.manager import manager

router = APIRouter()

WS_POLICY_VIOLATION = 1008


def _authenticate(token: Optional[str]):
    """Returns (user_id, role) or None. Runs in a worker thread (blocking DB)."""
    db = SessionLocal()
    try:
        user = user_from_token(db, token)
        return user.id, user.role
    except HTTPException:
        return None
    finally:
        db.close()


def _order_snapshot(order_id: int, user_id: int, role: str):
    """Returns (allowed, payload). Only customer / owner / assigned partner / admin may join."""
    db = SessionLocal()
    try:
        order = db.get(Order, order_id)
        if order is None:
            return False, "Order not found"
        allowed = False
        if role == Role.ADMIN:
            allowed = True
        elif role == Role.CUSTOMER:
            allowed = order.customer_id == user_id
        elif role == Role.OWNER:
            allowed = order.restaurant.owner_id == user_id
        elif role == Role.PARTNER:
            allowed = order.partner is not None and order.partner.user_id == user_id
        if not allowed:
            return False, "You are not allowed to track this order"
        return True, events.tracking_payload(order, event="snapshot")
    finally:
        db.close()


def _save_partner_location(user_id: int, lat: float, lon: float):
    from app.routers.partners import save_location

    db = SessionLocal()
    try:
        partner = db.query(DeliveryPartner).filter(DeliveryPartner.user_id == user_id).first()
        if partner is None or not partner.is_approved:
            return False
        save_location(db, partner, lat, lon)
        return True
    finally:
        db.close()


async def _reject(ws: WebSocket, reason: str):
    await ws.accept()
    await ws.send_json({"type": "error", "message": reason})
    await ws.close(code=WS_POLICY_VIOLATION, reason=reason)


async def _listen(ws: WebSocket, room: str):
    """Keep the socket open until the client disconnects; always clean up."""
    try:
        while True:
            await ws.receive_text()  # ignore pings / chatter
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(room, ws)


@router.websocket("/ws/orders/{order_id}")
async def ws_order_tracking(ws: WebSocket, order_id: int, token: Optional[str] = None):
    auth = await run_in_threadpool(_authenticate, token)
    if auth is None:
        return await _reject(ws, "Invalid or expired token")
    user_id, role = auth
    allowed, payload = await run_in_threadpool(_order_snapshot, order_id, user_id, role)
    if not allowed:
        return await _reject(ws, payload)
    room = f"order:{order_id}"
    await manager.connect(room, ws)
    await ws.send_json(_jsonable(payload))
    await _listen(ws, room)


async def _role_socket(ws: WebSocket, token: Optional[str], role: str, room_prefix: str, handle_location=False):
    auth = await run_in_threadpool(_authenticate, token)
    if auth is None:
        return await _reject(ws, "Invalid or expired token")
    user_id, user_role = auth
    if user_role != role:
        return await _reject(ws, "Forbidden for your role")
    room = f"{room_prefix}:{user_id}" if room_prefix != "admin" else "admin"
    await manager.connect(room, ws)
    await ws.send_json({"type": "connected", "room": room})
    try:
        while True:
            msg = await ws.receive_json()
            if handle_location and isinstance(msg, dict) and msg.get("type") == "location":
                try:
                    lat, lon = float(msg["latitude"]), float(msg["longitude"])
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        raise ValueError
                except (KeyError, ValueError, TypeError):
                    await ws.send_json({"type": "error", "message": "Invalid latitude/longitude"})
                    continue
                ok = await run_in_threadpool(_save_partner_location, user_id, lat, lon)
                await ws.send_json({"type": "location_saved" if ok else "error",
                                    **({} if ok else {"message": "Partner not approved"})})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(room, ws)


def _jsonable(data):
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(data)


@router.websocket("/ws/restaurant")
async def ws_restaurant(ws: WebSocket, token: Optional[str] = None):
    await _role_socket(ws, token, Role.OWNER, "restaurant")


@router.websocket("/ws/partner")
async def ws_partner(ws: WebSocket, token: Optional[str] = None):
    """Receives delivery offers; may also SEND {"type":"location","latitude":..,"longitude":..}."""
    await _role_socket(ws, token, Role.PARTNER, "partner", handle_location=True)


@router.websocket("/ws/customer")
async def ws_customer(ws: WebSocket, token: Optional[str] = None):
    """Customer notifications (e.g. order auto-rejected)."""
    await _role_socket(ws, token, Role.CUSTOMER, "customer")


@router.websocket("/ws/admin")
async def ws_admin(ws: WebSocket, token: Optional[str] = None):
    """Admin alerts (unassigned orders, locked deliveries)."""
    await _role_socket(ws, token, Role.ADMIN, "admin")
