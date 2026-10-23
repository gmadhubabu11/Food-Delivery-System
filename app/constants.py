"""Shared constants: roles, statuses and business rules."""


class Role:
    ADMIN = "admin"
    OWNER = "restaurant_owner"
    PARTNER = "delivery_partner"
    CUSTOMER = "customer"


PUBLIC_ROLES = (Role.OWNER, Role.PARTNER, Role.CUSTOMER)


class OrderStatus:
    PLACED = "Placed"
    ACCEPTED = "Accepted"
    PREPARING = "Preparing"
    READY = "Ready for Pickup"
    PICKED_UP = "Picked Up"
    OUT_FOR_DELIVERY = "Out for Delivery"
    DELIVERED = "Delivered"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"


# statuses in which a partner is considered busy with the delivery
ACTIVE_DELIVERY_STATUSES = (
    OrderStatus.ACCEPTED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.PICKED_UP,
    OrderStatus.OUT_FOR_DELIVERY,
)
# statuses where an order still needs (or has) a partner but is not finished
ASSIGNABLE_STATUSES = (OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY)


class PaymentMethod:
    COD = "COD"
    ONLINE = "Online"


class PaymentStatus:
    PENDING = "Pending"
    PAID = "Paid"
    REFUNDED = "Refunded"


class OfferStatus:
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    DECLINED = "Declined"
    EXPIRED = "Expired"


class DiscountType:
    PERCENTAGE = "Percentage"
    FLAT = "Flat"


# ---- business rules ----
OFFER_TTL_SECONDS = 30
PARTNER_SEARCH_RADIUS_KM = 5.0
AUTO_REJECT_AFTER_MINUTES = 5
UNASSIGNED_ALERT_AFTER_MINUTES = 15
PARTNER_INACTIVE_MINUTES = 10
MAX_OTP_ATTEMPTS = 3
TRAVEL_SPEED_KMPH = 20.0
MAX_ITEM_QUANTITY = 10

BASE_DELIVERY_FEE = 20
BASE_DELIVERY_KM = 3
EXTRA_KM_FEE = 8
PLATFORM_FEE = 5
GST_PERCENT = 5
PARTNER_BASE_EARNING = 25
PARTNER_PER_KM_EARNING = 6
SURGE_MULTIPLIER = 1.5
SURGE_WINDOWS = ((12, 14), (19, 22))
