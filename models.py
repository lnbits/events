import json
from datetime import datetime
from typing import Optional

from fastapi import Query
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
    wallet: Optional[str] = None
    name: str  # title (required)
    info: str = ""  # description (optional, visible by default)
    closing_date: Optional[str] = None  # defaults to event_end_date or event_start_date
    event_start_date: str  # required
    event_end_date: Optional[str] = None  # defaults to event_start_date
    currency: str = "sat"
    amount_tickets: int = 0  # 0 = unlimited / not ticketed
    price_per_ticket: float = 0  # 0 = free
    banner: Optional[str] = None  # image URL (optional, visible by default)
    location: Optional[str] = None  # venue/address (optional, visible by default)
    categories: list[str] = Field(default_factory=list)  # NIP-52 't' tags
    extra: EventExtra = Field(default_factory=EventExtra)
    status: str = "approved"  # proposed, approved, rejected


class CreateTicket(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    user_id: Optional[str] = None
    promo_code: Optional[str] = None
    refund_address: Optional[str] = None

    @root_validator
    def validate_identifiers(cls, values):
        # Ensure either (name AND email) OR user_id is provided
        name = values.get('name')
        email = values.get('email')
        user_id = values.get('user_id')

        if not user_id and not (name and email):
            raise ValueError("Either user_id or both name and email must be provided")
        if user_id and (name or email):
            raise ValueError("Cannot provide both user_id and name/email")
        return values


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
    status: str = "approved"  # proposed, approved, rejected
    nostr_event_id: str | None = None
    nostr_event_created_at: int | None = None

    @validator("categories", pre=True)
    def parse_categories(cls, v):
        if isinstance(v, str):
            return json.loads(v) if v else []
        return v or []


class EventsSettings(BaseModel):
    """Extension-level settings for the events extension."""

    auto_approve: bool = False  # Skip approval for all users


class TicketExtra(BaseModel):
    applied_promo_code: str | None = None
    sats_paid: int | None = None
    refund_address: str | None = None
    refunded: bool = False


class Ticket(BaseModel):
    id: str
    wallet: str
    event: str
    name: Optional[str] = None
    email: Optional[str] = None
    user_id: Optional[str] = None
    registered: bool
    paid: bool
    time: datetime
    reg_timestamp: datetime
    extra: TicketExtra = Field(default_factory=TicketExtra)
