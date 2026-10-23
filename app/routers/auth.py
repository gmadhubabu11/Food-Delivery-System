from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.constants import Role
from app.database import get_db
from app.models import DeliveryPartner, User
from app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "Email already registered")
    if data.role == Role.PARTNER and db.query(DeliveryPartner).filter(
        DeliveryPartner.vehicle_number == data.vehicle_number.upper()
    ).first():
        raise HTTPException(409, "Vehicle number already registered")

    user = User(
        name=data.name, email=email, phone=data.phone, password_hash=hash_password(data.password),
        role=data.role, is_active=True,
        is_approved=(data.role == Role.CUSTOMER),  # owners & partners need admin approval
    )
    db.add(user)
    db.flush()
    if data.role == Role.PARTNER:
        db.add(DeliveryPartner(
            user_id=user.id, vehicle_type=data.vehicle_type,
            vehicle_number=data.vehicle_number.upper(), is_approved=False,
        ))
    db.commit()
    db.refresh(user)
    return user


def _login(db: Session, email: str, password: str) -> TokenOut:
    user = db.query(User).filter(User.email == email.lower()).first()
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "Account is inactive")
    return TokenOut(access_token=create_access_token(user.id, user.role))


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    return _login(db, data.email, data.password)


@router.post("/token", response_model=TokenOut, include_in_schema=True)
def login_form(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Form-based login used by the Swagger 'Authorize' button (username = email)."""
    return _login(db, form.username, form.password)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
