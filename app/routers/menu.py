from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_approved_owner
from app.database import get_db
from app.models import CartItem, MenuCategory, MenuItem, Restaurant, User
from app.routers.restaurants import get_owned_restaurant
from app.schemas.restaurant import (
    AvailabilityIn, CategoryCreate, CategoryOut, MenuCategoryOut, MenuItemCreate, MenuItemOut,
    MenuItemUpdate, MenuOut,
)
from app.utils.clock import is_restaurant_open

router = APIRouter(tags=["Menu"])


def item_out(i: MenuItem) -> MenuItemOut:
    out = MenuItemOut.model_validate(i)
    out.unavailable = not i.is_available
    return out


def get_owned_item(db: Session, item_id: int, owner: User) -> MenuItem:
    item = db.get(MenuItem, item_id)
    if item is None or item.is_deleted:
        raise HTTPException(404, "Menu item not found")
    if item.restaurant.owner_id != owner.id:
        raise HTTPException(403, "You can manage only your own restaurants' menus")
    return item


def _check_category(db: Session, category_id: int, restaurant_id: int):
    cat = db.get(MenuCategory, category_id)
    if cat is None or cat.restaurant_id != restaurant_id:
        raise HTTPException(400, "Category does not belong to this restaurant")


@router.post("/restaurants/{restaurant_id}/categories", response_model=CategoryOut, status_code=201)
def create_category(restaurant_id: int, data: CategoryCreate, db: Session = Depends(get_db),
                    owner: User = Depends(require_approved_owner)):
    get_owned_restaurant(db, restaurant_id, owner)
    cat = MenuCategory(restaurant_id=restaurant_id, name=data.name)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.post("/restaurants/{restaurant_id}/menu-items", response_model=MenuItemOut, status_code=201)
def create_menu_item(restaurant_id: int, data: MenuItemCreate, db: Session = Depends(get_db),
                     owner: User = Depends(require_approved_owner)):
    get_owned_restaurant(db, restaurant_id, owner)
    _check_category(db, data.category_id, restaurant_id)
    item = MenuItem(restaurant_id=restaurant_id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item_out(item)


@router.get("/restaurants/{restaurant_id}/menu", response_model=MenuOut)
def get_menu(restaurant_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    r = db.get(Restaurant, restaurant_id)
    if r is None:
        raise HTTPException(404, "Restaurant not found")
    categories = db.query(MenuCategory).filter(MenuCategory.restaurant_id == restaurant_id).order_by(MenuCategory.id).all()
    items = db.query(MenuItem).filter(
        MenuItem.restaurant_id == restaurant_id, MenuItem.is_deleted.is_(False)
    ).order_by(MenuItem.id).all()
    grouped = {c.id: [] for c in categories}
    for i in items:
        grouped.setdefault(i.category_id, []).append(item_out(i))
    return MenuOut(
        restaurant_id=r.id, restaurant_name=r.name, is_open=is_restaurant_open(r),
        categories=[MenuCategoryOut(id=c.id, name=c.name, items=grouped.get(c.id, [])) for c in categories],
    )


@router.put("/menu-items/{item_id}", response_model=MenuItemOut)
def update_menu_item(item_id: int, data: MenuItemUpdate, db: Session = Depends(get_db),
                     owner: User = Depends(require_approved_owner)):
    item = get_owned_item(db, item_id, owner)
    changes = data.model_dump(exclude_unset=True)
    if "category_id" in changes:
        _check_category(db, changes["category_id"], item.restaurant_id)
    for k, v in changes.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item_out(item)


@router.put("/menu-items/{item_id}/availability", response_model=MenuItemOut)
def set_availability(item_id: int, data: AvailabilityIn, db: Session = Depends(get_db),
                     owner: User = Depends(require_approved_owner)):
    item = get_owned_item(db, item_id, owner)
    item.is_available = data.is_available  # hidden from ordering, not deleted
    db.commit()
    db.refresh(item)
    return item_out(item)


@router.delete("/menu-items/{item_id}")
def delete_menu_item(item_id: int, db: Session = Depends(get_db), owner: User = Depends(require_approved_owner)):
    item = get_owned_item(db, item_id, owner)
    item.is_deleted = True  # soft delete: old orders still reference it
    item.is_available = False
    db.query(CartItem).filter(CartItem.menu_item_id == item.id).delete()
    db.commit()
    return {"detail": "Menu item deleted"}
