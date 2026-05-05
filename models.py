from datetime import datetime

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
    wallet: str
    name: str
    info: str
    closing_date: str
    event_start_date: str
    event_end_date: str
    currency: str = "sat"
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
    banner: str | None


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
