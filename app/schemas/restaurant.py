from datetime import datetime, time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RestaurantBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    cuisine_type: str = Field(..., min_length=2, max_length=100)
    address: str = Field(..., min_length=3, max_length=255)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    opening_time: time
    closing_time: time
    delivery_radius_km: float = Field(5, gt=0, le=100)
    min_order_value: float = Field(0, ge=0)
    avg_preparation_minutes: int = Field(20, gt=0, le=300)


class RestaurantCreate(RestaurantBase):
    @model_validator(mode="after")
    def _times(self):
        if self.opening_time >= self.closing_time:
            raise ValueError("opening_time must be before closing_time")
        return self


class RestaurantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    cuisine_type: Optional[str] = Field(None, min_length=2, max_length=100)
    address: Optional[str] = Field(None, min_length=3, max_length=255)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    delivery_radius_km: Optional[float] = Field(None, gt=0, le=100)
    min_order_value: Optional[float] = Field(None, ge=0)
    avg_preparation_minutes: Optional[int] = Field(None, gt=0, le=300)
    is_active: Optional[bool] = None


class OpenStatusIn(BaseModel):
    is_temporarily_closed: bool


class RestaurantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    cuisine_type: str
    address: str
    latitude: float
    longitude: float
    opening_time: time
    closing_time: time
    is_temporarily_closed: bool
    delivery_radius_km: float
    min_order_value: float
    avg_preparation_minutes: int
    average_rating: float
    is_active: bool
    is_open: bool = False
    created_at: datetime


class NearbyRestaurantOut(RestaurantOut):
    distance_km: float
    estimated_delivery_minutes: int


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int
    name: str


class MenuItemCreate(BaseModel):
    category_id: int
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    is_veg: bool = True
    packaging_charge: float = Field(0, ge=0)
    is_available: bool = True


class MenuItemUpdate(BaseModel):
    category_id: Optional[int] = None
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    is_veg: Optional[bool] = None
    packaging_charge: Optional[float] = Field(None, ge=0)


class AvailabilityIn(BaseModel):
    is_available: bool


class MenuItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int
    category_id: int
    name: str
    description: Optional[str] = None
    price: float
    is_veg: bool
    packaging_charge: float
    is_available: bool
    unavailable: bool = False


class MenuCategoryOut(BaseModel):
    id: int
    name: str
    items: List[MenuItemOut]


class MenuOut(BaseModel):
    restaurant_id: int
    restaurant_name: str
    is_open: bool
    categories: List[MenuCategoryOut]
