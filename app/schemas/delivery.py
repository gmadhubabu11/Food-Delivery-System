from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AvailabilityIn(BaseModel):
    is_online: bool


class LocationIn(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class PartnerOut(BaseModel):
    id: int
    user_id: int
    vehicle_type: str
    vehicle_number: str
    is_online: bool
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    last_location_at: Optional[datetime] = None
    is_approved: bool


class OfferOut(BaseModel):
    offer_id: int
    order_id: int
    order_number: str
    status: str
    restaurant_name: str
    pickup_distance_km: Optional[float] = None
    delivery_distance_km: float
    expected_earnings: float
    seconds_left: int
    expires_at: datetime
