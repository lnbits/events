from datetime import datetime

from fastapi import Query
from pydantic import BaseModel, EmailStr, Field, field_validator


class PromoCode(BaseModel):
    code: str
    discount_percent: float = 0
    description: Optional[str] = None

    @field_validator("discount_percent")
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


class CreateTicket(BaseModel):
    name: str
    email: EmailStr


class Event(BaseModel):
    id: str
    wallet: str
    name: str
    info: str
    closing_date: str
    event_start_date: str
    event_end_date: str
    currency: str
    amount_tickets: int
    price_per_ticket: float
    time: datetime
    sold: int = 0
    banner: str | None = None
    extra: EventExtra = Field(default_factory=EventExtra)


class TicketExtra(BaseModel):
    applied_promo_code: str | None = None
    discount_applied: float | None = None
    refund_address: str | None = None


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
