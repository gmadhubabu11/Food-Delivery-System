from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Literal

from app.utils.clock import to_local_naive


class CouponBase(BaseModel):
    description: Optional[str] = Field(None, max_length=255)
    discount_type: Literal["Percentage", "Flat"]
    discount_value: float = Field(..., gt=0)
    max_discount: Optional[float] = Field(None, gt=0)
    min_order_value: float = Field(0, ge=0)
    valid_from: datetime
    valid_to: datetime
    total_usage_limit: Optional[int] = Field(None, gt=0)
    per_user_limit: Optional[int] = Field(1, gt=0)
    first_order_only: bool = False

    @field_validator("valid_from", "valid_to")
    @classmethod
    def _local(cls, v):
        return to_local_naive(v)

    @model_validator(mode="after")
    def _rules(self):
        if self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        if self.discount_type == "Percentage" and not (1 <= self.discount_value <= 100):
            raise ValueError("Percentage coupons must have discount_value between 1 and 100")
        return self


class CouponCreate(CouponBase):
    code: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    restaurant_id: Optional[int] = None  # empty => platform-wide (admin only)


class CouponUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=255)
    discount_type: Optional[Literal["Percentage", "Flat"]] = None
    discount_value: Optional[float] = Field(None, gt=0)
    max_discount: Optional[float] = Field(None, gt=0)
    min_order_value: Optional[float] = Field(None, ge=0)
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    total_usage_limit: Optional[int] = Field(None, gt=0)
    per_user_limit: Optional[int] = Field(None, gt=0)
    first_order_only: Optional[bool] = None
    is_active: Optional[bool] = None

    @field_validator("valid_from", "valid_to")
    @classmethod
    def _local(cls, v):
        return to_local_naive(v) if v else v


class CouponOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    description: Optional[str] = None
    discount_type: str
    discount_value: float
    max_discount: Optional[float] = None
    min_order_value: float
    restaurant_id: Optional[int] = None
    valid_from: datetime
    valid_to: datetime
    total_usage_limit: Optional[int] = None
    per_user_limit: Optional[int] = None
    first_order_only: bool
    created_by: int
    is_active: bool


class AvailableCouponOut(BaseModel):
    code: str
    description: Optional[str] = None
    discount_type: str
    discount_value: float
    max_discount: Optional[float] = None
    min_order_value: float
    restaurant_id: Optional[int] = None
    valid_to: datetime
    discount: float
