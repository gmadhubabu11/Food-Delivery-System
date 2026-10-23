from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import require_customer
from app.database import get_db
from app.models import Address, User
from app.schemas.address import AddressCreate, AddressOut, AddressUpdate

router = APIRouter(prefix="/addresses", tags=["Addresses"])


def _own(db: Session, address_id: int, user: User) -> Address:
    a = db.query(Address).filter(
        Address.id == address_id, Address.customer_id == user.id, Address.is_deleted.is_(False)
    ).first()
    if a is None:
        raise HTTPException(404, "Address not found")
    return a


def _unset_defaults(db: Session, user: User, except_id: int = None):
    q = db.query(Address).filter(Address.customer_id == user.id, Address.is_default.is_(True))
    if except_id:
        q = q.filter(Address.id != except_id)
    for a in q.all():
        a.is_default = False


@router.post("", response_model=AddressOut, status_code=201)
def create_address(data: AddressCreate, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    has_any = db.query(Address).filter(Address.customer_id == user.id, Address.is_deleted.is_(False)).count() > 0
    a = Address(customer_id=user.id, **data.model_dump())
    if not has_any:
        a.is_default = True  # first address becomes default
    db.add(a)
    db.flush()
    if a.is_default:
        _unset_defaults(db, user, a.id)
    db.commit()
    db.refresh(a)
    return a


@router.get("", response_model=List[AddressOut])
def list_addresses(db: Session = Depends(get_db), user: User = Depends(require_customer)):
    return db.query(Address).filter(
        Address.customer_id == user.id, Address.is_deleted.is_(False)
    ).order_by(Address.is_default.desc(), Address.id).all()


@router.put("/{address_id}", response_model=AddressOut)
def update_address(address_id: int, data: AddressUpdate, db: Session = Depends(get_db),
                   user: User = Depends(require_customer)):
    a = _own(db, address_id, user)
    changes = data.model_dump(exclude_unset=True)
    make_default = changes.pop("is_default", None)
    for k, v in changes.items():
        setattr(a, k, v)
    if make_default:
        _unset_defaults(db, user, a.id)
        a.is_default = True
    db.commit()
    db.refresh(a)
    return a


@router.delete("/{address_id}")
def delete_address(address_id: int, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    a = _own(db, address_id, user)
    was_default = a.is_default
    a.is_deleted = True  # soft delete: old orders keep their address
    a.is_default = False
    db.flush()
    if was_default:
        nxt = db.query(Address).filter(
            Address.customer_id == user.id, Address.is_deleted.is_(False)
        ).order_by(Address.id.desc()).first()
        if nxt:
            nxt.is_default = True
    db.commit()
    return {"detail": "Address deleted"}


@router.put("/{address_id}/default", response_model=AddressOut)
def set_default(address_id: int, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    a = _own(db, address_id, user)
    _unset_defaults(db, user, a.id)
    a.is_default = True
    db.commit()
    db.refresh(a)
    return a
