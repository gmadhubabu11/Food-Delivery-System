from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")


def D(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def q(value) -> Decimal:
    """Round to 2 decimals (half-up)."""
    return D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt(value) -> str:
    """₹299 / ₹299.50 style formatting for messages."""
    v = q(value)
    return f"₹{int(v)}" if v == v.to_integral_value() else f"₹{v}"
