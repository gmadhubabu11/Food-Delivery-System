from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token, unauthorized
from app.constants import Role
from app.database import get_db
from app.models import DeliveryPartner, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def user_from_token(db: Session, token: Optional[str]) -> User:
    """Shared by REST and WebSocket auth. Raises 401 / 403 HTTPException."""
    if not token:
        raise unauthorized("Not authenticated")
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise unauthorized()
    try:
        user = db.get(User, int(payload["sub"]))
    except (ValueError, TypeError):
        raise unauthorized()
    if user is None:
        raise unauthorized()
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    return user


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    return user_from_token(db, token)


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to access this resource")
        return user

    return checker


require_admin = require_roles(Role.ADMIN)
require_customer = require_roles(Role.CUSTOMER)


def require_approved_owner(user: User = Depends(require_roles(Role.OWNER))) -> User:
    if not user.is_approved:
        raise HTTPException(status_code=403, detail="Your account is pending admin approval")
    return user


def get_partner_profile(
    user: User = Depends(require_roles(Role.PARTNER)), db: Session = Depends(get_db)
) -> DeliveryPartner:
    partner = db.query(DeliveryPartner).filter(DeliveryPartner.user_id == user.id).first()
    if partner is None:
        raise HTTPException(status_code=404, detail="Delivery partner profile not found")
    return partner


def get_approved_partner(partner: DeliveryPartner = Depends(get_partner_profile)) -> DeliveryPartner:
    if not partner.is_approved:
        raise HTTPException(status_code=403, detail="Your account is pending admin approval")
    return partner
