from datetime import datetime

from fastapi import Query
from pydantic import BaseModel, EmailStr, Field, validator


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
    email_notifications: bool = False
    nostr_notifications: bool = False


class CreateEvent(BaseModel):
    wallet: str
    name: str
    info: str
    closing_date: str
    event_start_date: str
    event_end_date: str
    currency: str = "sat"
    allow_fiat: bool = False
    fiat_currency: str = "GBP"
    amount_tickets: int = Query(..., ge=0)
    price_per_ticket: float = Query(..., ge=0)
    banner: str | None = None
    extra: EventExtra = Field(default_factory=EventExtra)


class Event(BaseModel):
    id: str
    wallet: str
    name: str
    info: str
    closing_date: str
    canceled: bool = False
    event_start_date: str
    event_end_date: str
    currency: str
    allow_fiat: bool = False
    fiat_currency: str = "GBP"
    amount_tickets: int
    price_per_ticket: float
    time: datetime
    sold: int = 0
    banner: str | None = None
    extra: EventExtra = Field(default_factory=EventExtra)


class PublicEvent(BaseModel):
    id: str
    name: str
    info: str
    closing_date: str
    canceled: bool
    event_start_date: str
    event_end_date: str
    currency: str
    allow_fiat: bool = False
    fiat_currency: str = "GBP"
    price_per_ticket: float
    banner: str | None
    extra: EventExtra = Field(default_factory=EventExtra)


class TicketExtra(BaseModel):
    applied_promo_code: str | None = None
    sats_paid: int | None = None
    refund_address: str | None = None
    nostr_identifier: str | None = None
    ticket_base_url: str | None = None
    email_notification_sent: bool = False
    nostr_notification_sent: bool = False
    refunded: bool = False


class CreateTicket(BaseModel):
    name: str
    email: EmailStr
    promo_code: str | None = None
    refund_address: str | None = None
    nostr_identifier: str | None = None
    payment_method: str | None = None
    fiat_provider: str | None = None


class Ticket(BaseModel):
    id: str
    wallet: str
    event: str
    name: str
    email: str
    registered: bool
    paid: bool
    time: datetime
    reg_timestamp: datetime
    extra: TicketExtra = Field(default_factory=TicketExtra)


class PublicTicket(BaseModel):
    event: str
    name: str
    registered: bool
    paid: bool
    time: datetime
    reg_timestamp: datetime


class TicketPaymentRequest(BaseModel):
    payment_hash: str
    payment_request: str | None = None
    fiat_payment_request: str | None = None
    fiat_provider: str | None = None
    is_fiat: bool = False
