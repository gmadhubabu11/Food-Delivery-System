from typing import List, Optional

from pydantic import BaseModel, Field


class CartItemIn(BaseModel):
    menu_item_id: int
    quantity: int = Field(1, ge=1, le=10)


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., ge=1, le=10)


class ApplyCouponIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)


class CartItemOut(BaseModel):
    id: int
    menu_item_id: int
    name: str
    is_veg: bool
    price: float
    quantity: int
    line_total: float
    is_available: bool


class CartOut(BaseModel):
    cart_id: int
    restaurant_id: Optional[int] = None
    restaurant_name: Optional[str] = None
    items: List[CartItemOut]
    item_total: float
    coupon_code: Optional[str] = None
    discount: float
    item_total_after_discount: float
    coupon_message: Optional[str] = None


class ReorderOut(BaseModel):
    cart: CartOut
    skipped_items: List[str]
