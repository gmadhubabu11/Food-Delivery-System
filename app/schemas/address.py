import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import Literal


def _pin(v):
    if v is not None and not re.fullmatch(r"\d{6}", v):
        raise ValueError("Pincode must be exactly 6 digits")
    return v


class AddressCreate(BaseModel):
    label: Literal["Home", "Work", "Other"]
    address_line: str = Field(..., min_length=3, max_length=255)
    city: str = Field(..., min_length=2, max_length=100)
    pincode: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    is_default: bool = False

    @field_validator("pincode")
    @classmethod
    def _check_pincode(cls, v):
        return _pin(v)


class AddressUpdate(BaseModel):
    label: Optional[Literal["Home", "Work", "Other"]] = None
    address_line: Optional[str] = Field(None, min_length=3, max_length=255)
    city: Optional[str] = Field(None, min_length=2, max_length=100)
    pincode: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    is_default: Optional[bool] = None

    @field_validator("pincode")
    @classmethod
    def _check_pincode(cls, v):
        return _pin(v)


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    label: str
    address_line: str
    city: str
    pincode: str
    latitude: float
    longitude: float
    is_default: bool
    created_at: datetime
