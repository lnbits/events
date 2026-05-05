import json
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, root_validator, validator


class PromoCode(BaseModel):
    code: str
    discount_percent: float = 0.0
    active: bool = True

    # make the promo code uppercase
    @validator("code")
    def uppercase_code(cls, v):
        return v.upper()

    @validator("discount_percent")
    def validate_discount_percent(cls, v):
        assert 0 <= v <= 100, "Discount must be between 0 and 100."
        return v


class EventExtra(BaseModel):
    promo_codes: list[PromoCode] = Field(default_factory=list)
    conditional: bool = False
    min_tickets: int = 1


class CreateEvent(BaseModel):
    wallet: str | None = None  # filled from caller's wallet if absent
    name: str  # title (required)
    info: str = ""  # description (optional)
    closing_date: str | None = None  # defaults to event_end_date
    event_start_date: str  # required
    event_end_date: str | None = None  # defaults to event_start_date
    currency: str = "sat"
    amount_tickets: int = 0  # 0 = unlimited / not ticketed
    price_per_ticket: float = 0  # 0 = free
    banner: str | None = None
    location: str | None = None  # venue/address (NIP-52 'location' tag)
    categories: list[str] = Field(default_factory=list)  # NIP-52 't' tags
    extra: EventExtra = Field(default_factory=EventExtra)
    status: str = "approved"  # proposed, approved, rejected


class Event(BaseModel):
    id: str
    wallet: str
    name: str
    info: str = ""
    closing_date: str | None = None
    canceled: bool = False
    event_start_date: str
    event_end_date: str | None = None
    currency: str = "sat"
    amount_tickets: int = 0
    price_per_ticket: float = 0
    time: datetime
    sold: int = 0
    banner: str | None = None
    location: str | None = None
    categories: list[str] = Field(default_factory=list)
    extra: EventExtra = Field(default_factory=EventExtra)
    status: str = "approved"
    nostr_event_id: str | None = None
    nostr_event_created_at: int | None = None

    @validator("categories", pre=True)
    def parse_categories(cls, v):
        if isinstance(v, str):
            return json.loads(v) if v else []
        return v or []


class PublicEvent(BaseModel):
    id: str
    name: str
    info: str
    closing_date: str | None = None
    canceled: bool
    event_start_date: str
    event_end_date: str | None = None
    banner: str | None
    location: str | None = None
    categories: list[str] = Field(default_factory=list)
    status: str = "approved"  # surfaces "proposed"/"rejected" so SFC can render banner

    @validator("categories", pre=True)
    def parse_categories(cls, v):
        if isinstance(v, str):
            return json.loads(v) if v else []
        return v or []


class EventsSettings(BaseModel):
    """Extension-level settings for the events extension."""

    auto_approve: bool = False  # Skip approval workflow for non-admin users


class TicketExtra(BaseModel):
    applied_promo_code: str | None = None
    sats_paid: int | None = None
    refund_address: str | None = None
    refunded: bool = False


class CreateTicket(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    user_id: str | None = None  # LNbits user id (alternative to name+email)
    promo_code: str | None = None
    refund_address: str | None = None

    @root_validator
    def validate_identifiers(cls, values):
        name = values.get("name")
        email = values.get("email")
        user_id = values.get("user_id")
        if not user_id and not (name and email):
            raise ValueError(
                "Either user_id or both name and email must be provided"
            )
        if user_id and (name or email):
            raise ValueError("Cannot provide both user_id and name/email")
        return values


class Ticket(BaseModel):
    id: str
    wallet: str
    event: str
    name: str | None = None
    email: str | None = None
    user_id: str | None = None
    registered: bool
    paid: bool
    time: datetime
    reg_timestamp: datetime
    extra: TicketExtra = Field(default_factory=TicketExtra)


class PublicTicket(BaseModel):
    event: str
    name: str | None = None
    registered: bool
    paid: bool
    time: datetime
    reg_timestamp: datetime


class TicketPaymentRequest(BaseModel):
    payment_hash: str
    payment_request: str
