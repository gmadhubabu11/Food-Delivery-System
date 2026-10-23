from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RatingCreate(BaseModel):
    restaurant_rating: int = Field(..., ge=1, le=5)
    partner_rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)


class RatingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    customer_id: int
    restaurant_id: int
    partner_id: Optional[int] = None
    restaurant_rating: int
    partner_rating: int
    comment: Optional[str] = None
    created_at: datetime
