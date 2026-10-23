from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Literal


class OrderCreate(BaseModel):
    address_id: int
    payment_method: Literal["COD", "Online"]
    tip_amount: float = Field(0, ge=0)


class AcceptIn(BaseModel):
    estimated_preparation_minutes: int = Field(..., gt=0, le=300)


class RejectIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=255)


class OTPIn(BaseModel):
    otp: str = Field(..., pattern=r"^\d{4}$")


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    menu_item_id: int
    item_name: str
    price: float
    quantity: int
    packaging_charge: float
    line_total: float


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_status: Optional[str] = None
    new_status: str
    changed_by: str
    note: Optional[str] = None
    created_at: datetime


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    customer_id: int
    restaurant_id: int
    address_id: int
    delivery_partner_id: Optional[int] = None
    item_total: float
    coupon_code: Optional[str] = None
    discount_amount: float
    packaging_charges: float
    delivery_fee: float
    platform_fee: float
    gst_amount: float
    tip_amount: float
    grand_total: float
    payment_method: str
    payment_status: str
    status: str
    distance_km: float
    delivery_otp: Optional[str] = None  # only visible to the customer
    rejection_reason: Optional[str] = None
    estimated_preparation_minutes: Optional[int] = None
    placed_at: datetime
    delivered_at: Optional[datetime] = None
    items: List[OrderItemOut] = []
    history: List[HistoryOut] = []
