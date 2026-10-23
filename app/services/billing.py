import math
from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.config import settings
from app.constants import (
    BASE_DELIVERY_FEE, BASE_DELIVERY_KM, EXTRA_KM_FEE, GST_PERCENT, PLATFORM_FEE,
    SURGE_MULTIPLIER, SURGE_WINDOWS,
)
from app.utils.clock import now
from app.utils.money import D, q


def surge_multiplier(at: Optional[datetime] = None) -> Decimal:
    if not settings.SURGE_PRICING_ENABLED:
        return Decimal("1")
    hour = (at or now()).hour
    for start, end in SURGE_WINDOWS:
        if start <= hour < end:
            return D(SURGE_MULTIPLIER)
    return Decimal("1")


def delivery_fee(distance_km: float, at: Optional[datetime] = None) -> Decimal:
    """Rs 20 for the first 3 km + Rs 8 for every extra km (rounded up)."""
    extra_km = max(0, math.ceil(round(float(distance_km), 2) - BASE_DELIVERY_KM))
    fee = D(BASE_DELIVERY_FEE) + D(EXTRA_KM_FEE) * extra_km
    return q(fee * surge_multiplier(at))


def calculate_bill(item_total, discount, packaging, distance_km, tip=0, at: Optional[datetime] = None) -> dict:
    item_total, discount, packaging, tip = q(item_total), q(discount), q(packaging), q(tip)
    after_discount = item_total - discount
    fee = delivery_fee(distance_km, at)
    platform = q(PLATFORM_FEE)
    gst = q(after_discount * D(GST_PERCENT) / D(100))
    grand = q(after_discount + packaging + fee + platform + gst + tip)
    return {
        "item_total": item_total,
        "discount_amount": discount,
        "packaging_charges": packaging,
        "delivery_fee": fee,
        "platform_fee": platform,
        "gst_amount": gst,
        "tip_amount": tip,
        "grand_total": grand,
    }
