import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from typing_extensions import Literal


class RegisterIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: str
    password: str = Field(..., min_length=6, max_length=72)
    role: Literal["customer", "restaurant_owner", "delivery_partner"]
    vehicle_type: Optional[Literal["Bike", "Scooter", "Bicycle"]] = None
    vehicle_number: Optional[str] = Field(None, max_length=20)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        if not re.fullmatch(r"\d{10}", v):
            raise ValueError("Phone number must be exactly 10 digits")
        return v

    @model_validator(mode="after")
    def _partner_fields(self):
        if self.role == "delivery_partner" and not (self.vehicle_type and self.vehicle_number):
            raise ValueError("vehicle_type and vehicle_number are required for delivery partners")
        return self


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str
    role: str
    is_active: bool
    is_approved: bool
    created_at: datetime


class ActiveStatusIn(BaseModel):
    is_active: bool
