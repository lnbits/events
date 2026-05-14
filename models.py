from datetime import date, datetime
from uuid import uuid4
import json

from fastapi import Query
from lnbits.db import FilterModel
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


class TicketWave(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    title: str = "Primary wave"
    opening_date: str
    closing_date: str
    currency: str = "sat"
    use_ticket_image: bool = False
    ticket_image_id: str | None = None
    allow_fiat: bool = False
    fiat_currency: str = "GBP"
    amount_tickets: int = Field(default=0, ge=0)
    price_per_ticket: float = Field(default=0, ge=0)


class EventExtra(BaseModel):
    promo_codes: list[PromoCode] = Field(default_factory=list)
    ticket_waves: list[TicketWave] = Field(default_factory=list)
    conditional: bool = False
    min_tickets: int = 1
    email_notifications: bool = False
    nostr_notifications: bool = False
    notification_subject: str = ""
    notification_body: str = ""


class CreateEvent(BaseModel):
    wallet: str | None = None  # filled from caller's wallet if absent
    name: str  # title (required)
    info: str = ""  # description (optional)
    closing_date: str | None = None  # defaults to event_end_date
    event_start_date: str  # required
    event_end_date: str | None = None  # defaults to event_start_date
    currency: str = "sat"
    allow_fiat: bool = False
    fiat_currency: str = "GBP"
    amount_tickets: int = Query(..., ge=0)
    price_per_ticket: float = Query(..., ge=0)
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
    event_end_date: str
    currency: str
    allow_fiat: bool = False
    fiat_currency: str = "GBP"
    amount_tickets: int
    price_per_ticket: float
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
    event_end_date: str
    currency: str
    allow_fiat: bool = False
    fiat_currency: str = "GBP"
    price_per_ticket: float
    banner: str | None
    extra: EventExtra = Field(default_factory=EventExtra)
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
    ticket_wave_id: str | None = None
    ticket_wave_title: str | None = None
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
    ticket_wave_id: str | None = None
    promo_code: str | None = None
    refund_address: str | None = None
    nostr_identifier: str | None = None
    payment_method: str | None = None
    fiat_provider: str | None = None

    @root_validator
    def validate_identifiers(cls, values):
        name = values.get("name")
        email = values.get("email")
        user_id = values.get("user_id")
        if not user_id and not (name and email):
            raise ValueError("Either user_id or both name and email must be provided")
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


class NotificationDeliveryResult(BaseModel):
    attempted: bool = False
    sent: bool = False
    error: str | None = None


class TicketResendResult(BaseModel):
    ticket: Ticket
    email: NotificationDeliveryResult = Field(
        default_factory=NotificationDeliveryResult
    )
    nostr: NotificationDeliveryResult = Field(
        default_factory=NotificationDeliveryResult
    )


class PublicTicket(BaseModel):
    event: str
    name: str | None = None
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


class TicketFilters(FilterModel):
    __search_fields__ = ["event", "name", "email", "id"]  # noqa: RUF012
    __sort_fields__ = [  # noqa: RUF012
        "time",
        "event",
        "name",
        "email",
        "registered",
        "id",
    ]

    event: str | None = None
    name: str | None = None
    email: str | None = None
    registered: bool | None = None
    paid: bool | None = None
    id: str | None = None


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def ensure_ticket_waves(event: Event | PublicEvent | CreateEvent) -> list[TicketWave]:
    ticket_waves = list(getattr(event.extra, "ticket_waves", []) or [])
    if ticket_waves:
        return ticket_waves

    fallback_opening_date = None
    event_time = getattr(event, "time", None)
    if event_time:
        fallback_opening_date = event_time.date().isoformat()
    if not fallback_opening_date:
        fallback_opening_date = event.closing_date

    return [
        TicketWave(
            id="primary",
            title="Primary wave",
            opening_date=fallback_opening_date,
            closing_date=event.closing_date,
            currency=event.currency,
            allow_fiat=event.allow_fiat,
            fiat_currency=event.fiat_currency,
            amount_tickets=getattr(event, "amount_tickets", 0),
            price_per_ticket=event.price_per_ticket,
        )
    ]


def sync_event_ticket_waves(event: Event | CreateEvent) -> Event | CreateEvent:
    ticket_waves = ensure_ticket_waves(event)
    event.extra.ticket_waves = ticket_waves

    primary_wave = ticket_waves[0]
    event.closing_date = max(wave.closing_date for wave in ticket_waves)
    event.currency = primary_wave.currency
    event.allow_fiat = primary_wave.allow_fiat
    event.fiat_currency = primary_wave.fiat_currency
    event.amount_tickets = sum(wave.amount_tickets for wave in ticket_waves)
    event.price_per_ticket = primary_wave.price_per_ticket

    return event


def get_active_ticket_waves(
    event: Event | PublicEvent, today: date | None = None
) -> list[TicketWave]:
    current_day = today or datetime.utcnow().date()
    return [
        wave
        for wave in ensure_ticket_waves(event)
        if _parse_date(wave.opening_date)
        <= current_day
        <= _parse_date(wave.closing_date)
        and wave.amount_tickets > 0
    ]
