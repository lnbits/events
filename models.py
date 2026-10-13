from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import Query
from lnbits.db import FilterModel
from pydantic import BaseModel, Field, root_validator, validator


class PromoSource(BaseModel):
    """The source-ticket condition attached to a promo.

    Orthogonal to the offer code: a promo identifies itself with ``code`` and
    ADDITIONALLY may require an existing ticket. ``require_ticket=False`` is the
    classic typed-code promo; ``require_ticket=True`` makes the rule an offer
    code that only applies when a valid source ticket is presented too (ticket
    upgrades and extra-ticket offers).

    ``event_ids``/``ticket_type_ids`` scope which source tickets qualify (empty
    event_ids = the target event only), ``move`` turns it into an upgrade (void
    the source and release its seat on payment), and ``credit`` adds the source
    ticket's recorded paid value to the discount.
    """

    require_ticket: bool = False
    event_ids: list[str] | None = None
    ticket_type_ids: list[str] | None = None
    move: bool = False
    credit: str = "none"

    @validator("credit")
    def validate_credit(cls, v):
        assert v in ("none", "paid"), "source credit must be 'none' or 'paid'."
        return v

    @root_validator
    def drop_ticket_condition_without_ticket(cls, values):
        # Coerce rather than raise: this JSON is parsed on every read, so a
        # stored row with `move`/`credit` but no ticket requirement must not
        # make the whole event unloadable. Those flags are meaningless without
        # a ticket, so they simply fall away.
        if not values.get("require_ticket", False):
            values["move"] = False
            values["credit"] = "none"
        return values


class PromoGrant(BaseModel):
    """The add-on entitlement a promo may carry INSTEAD of a discount.

    A grant rule authorises the buyer to ADD tickets of ``ticket_type_id`` to
    the basket — up to ``per_source`` for every person the source ticket
    admits — and only while a qualifying source ticket is present (already in
    the basket, or presented by id). This is how a free add-on ticket such as
    a Bitflix screening seat is gated: the entitlement is the effect, so no
    discount maths is involved.
    """

    ticket_type_id: str
    per_source: int = 1

    @validator("per_source")
    def validate_per_source(cls, v):
        assert v >= 1, "per_source must be >= 1."
        return v


class PromoCode(BaseModel):
    """A discount rule.

    ``code`` identifies the offer to the buyer and is the primary key for
    matching. ``source.require_ticket`` additionally demands a valid existing
    ticket, which is what enables upgrades and extra-ticket offers; a ticket
    rule may leave ``code`` blank to mean "any eligible ticket activates this".
    """

    code: str = ""
    # Human-readable name for the offer, shown in the admin and at checkout.
    # A code-less rule (one activated by presenting a ticket) has no identifier
    # of its own, so without this it is unidentifiable in the promo list.
    title: str = ""
    discount_percent: float | None = None
    discount_fixed: int | None = None
    active: bool = True
    combinable: bool = True
    max_uses: int | None = None
    used_count: int = 0
    source: PromoSource = Field(default_factory=PromoSource)
    redemptions_per_ticket: int = 1
    # TARGET scope: when set, the discount only applies to the value of the
    # listed ticket types (by ticket_type_id). None/empty = basket-wide.
    ticket_type_ids: list[str] | None = None
    # Max number of tickets a single redemption can cover (None = any number).
    # Contrast redemptions_per_ticket (how many times the same source ticket
    # can be redeemed).
    max_tickets: int | None = None
    # Add-on entitlement: when set, this rule GRANTS tickets of another type
    # rather than discounting the basket. Requires a source ticket like every
    # other ticket rule, and is mutually exclusive with a discount.
    grants: PromoGrant | None = None
    # Runtime-only: set when a ticket rule is resolved, carrying the credit
    # derived from the source ticket. Never persisted as configuration.
    credit_value: float | None = None

    @root_validator(pre=True)
    def migrate_legacy_axis(cls, values):
        # Rows written before the offer-code axis stored `type: "code"|"ticket"`
        # and, for ticket rules, the sentinel code "TICKETID"; rows written by
        # the intermediate revision stored `source.kind`. Map both onto
        # `source.require_ticket` so existing config keeps working.
        if not isinstance(values, dict):
            return values

        legacy_type = values.pop("type", None)
        source = values.get("source")
        if isinstance(source, dict) and "kind" in source:
            source.setdefault("require_ticket", source.pop("kind") == "ticket")
        elif legacy_type is not None and "source" not in values:
            values["source"] = {"require_ticket": legacy_type == "ticket"}

        source = values.get("source")
        require_ticket = bool(
            source.get("require_ticket") if isinstance(source, dict) else False
        )
        # The retired sentinel was never a real code.
        if require_ticket and (values.get("code") or "") == "TICKETID":
            values["code"] = ""
        return values

    @validator("code")
    def uppercase_code(cls, v):
        return v.upper()

    @validator("redemptions_per_ticket")
    def validate_redemptions_per_ticket(cls, v):
        assert v is not None and v >= 1, "redemptions_per_ticket must be >= 1."
        return v

    @validator("max_tickets")
    def validate_max_tickets(cls, v):
        if v is not None:
            assert v >= 1, "max_tickets must be >= 1."
        return v

    @validator("discount_percent")
    def validate_discount_percent(cls, v):
        if v is not None:
            assert 0 <= v <= 100, "Discount must be between 0 and 100."
        return v

    @validator("discount_fixed")
    def validate_discount_fixed(cls, v):
        if v is not None:
            assert v >= 0, "Fixed discount must be >= 0."
        return v

    @root_validator
    def validate_code_present(cls, values):
        # A code is required unless the rule is activated by a ticket alone.
        source = values.get("source")
        require_ticket = getattr(source, "require_ticket", False)
        if not require_ticket and not (values.get("code") or "").strip():
            raise ValueError(
                "a promo code is required unless the rule requires a ticket"
            )
        return values

    @root_validator
    def validate_discount_exclusive(cls, values):
        percent = values.get("discount_percent")
        fixed = values.get("discount_fixed")
        if percent is not None and fixed is not None:
            values["discount_fixed"] = None
        return values

    @root_validator(pre=True)
    def coerce_grant_requires_source(cls, values):
        # A grant needs a source ticket to gate on, so it IMPLIES the source
        # gate. A discount is deliberately NOT cleared here: a grant rule is
        # dropped from the discount engine entirely, so a retained discount is
        # inert, and clearing it would silently destroy a value the admin typed
        # (see test_grant_keeps_and_ignores_a_discount).
        # Coerce rather than raise: this JSON is parsed on every read, so a
        # stale row must not unload the event. pre=True so this runs BEFORE
        # `validate_code_present`, which would otherwise reject the codeless
        # rule such a row leaves behind.
        if not isinstance(values, dict) or values.get("grants") is None:
            return values
        source = values.get("source")
        if isinstance(source, dict):
            source["require_ticket"] = True
        elif source is None:
            values["source"] = {"require_ticket": True}
        elif not getattr(source, "require_ticket", False):
            values["source"] = {**source.dict(), "require_ticket": True}
        return values


class TicketType(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    event_id: str
    name: str = "General Admission"
    description: str = ""
    image_url: str | None = None
    price: float = Field(default=0, ge=0)
    max_tickets: int = Field(default=0, ge=0)
    sold: int = 0
    available_from: str
    available_to: str
    sort_order: int = 0
    extra: dict = Field(default_factory=dict)


class EventExtra(BaseModel):
    promo_codes: list[PromoCode] = Field(default_factory=list)
    conditional: bool = False
    min_tickets: int = 1
    email_notifications: bool = False
    nostr_notifications: bool = False
    notification_subject: str = ""
    notification_body: str = ""
    payment_methods: list[str] = Field(default_factory=list)
    ln_wallet_id: str | None = None
    onchain_wallet_id: str | None = None
    fiat_provider: str | None = None


class CreateEvent(BaseModel):
    wallet: str
    name: str
    info: str
    event_start_date: str
    event_end_date: str
    currency: str = "sat"
    allow_fiat: bool = False
    fiat_currency: str = "GBP"
    admin_email: str | None = None
    amount_tickets: int = Query(default=0, ge=0)
    price_per_ticket: float = Query(default=0, ge=0)
    banner: str | None = None
    extra: EventExtra = Field(default_factory=EventExtra)


class Event(BaseModel):
    id: str
    wallet: str
    name: str
    info: str
    canceled: bool = False
    event_start_date: str
    event_end_date: str
    currency: str
    admin_email: str | None = None
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
    canceled: bool
    event_start_date: str
    event_end_date: str
    currency: str
    admin_email: str | None = None
    allow_fiat: bool = False
    fiat_currency: str = "GBP"
    banner: str | None
    extra: EventExtra = Field(default_factory=EventExtra)


class TicketExtra(BaseModel):
    applied_promo_code: str | None = None
    ticket_wave_id: str | None = None
    ticket_wave_title: str | None = None
    ticket_type_id: str | None = None
    sats_paid: int | None = None
    refund_address: str | None = None
    nostr_identifier: str | None = None
    ticket_base_url: str | None = None
    email_notification_sent: bool = False
    nostr_notification_sent: bool = False
    refunded: bool = False
    deactivated: bool = False
    satspay_charge_id: str | None = None
    ticket_id_voucher_redemptions: list = Field(default_factory=list)
    # Amount actually charged for this ticket, in the event's currency.
    # Recorded on payment; used as the credit basis when the ticket is later
    # upgraded. Deriving credit from what was paid (not the ticket type's face
    # price) means a chain of upgrades can never inflate its own value.
    paid_value: float | None = None
    # Set on a source ticket consumed by a move upgrade.
    upgraded_to: str | None = None
    # Set on a ticket created by a move upgrade.
    upgraded_from: str | None = None


class CreateTicket(BaseModel):
    name: str
    email: str | None = None
    ticket_type_id: str | None = None
    ticket_wave_id: str | None = None
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
    reg_timestamp: datetime | None = None
    ticket_type_id: str | None = None
    basket_id: str | None = None
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
    event_name: str = ""
    ticket_type_name: str = ""
    name: str
    email: str | None = None
    registered: bool
    paid: bool
    deactivated: bool = False
    time: datetime
    reg_timestamp: datetime | None = None


class TicketPaymentRequest(BaseModel):
    payment_hash: str
    payment_request: str | None = None
    fiat_payment_request: str | None = None
    fiat_provider: str | None = None
    is_fiat: bool = False
    onchain_amount_sat: int | None = None
    satspay_charge_url: str | None = None
    basket_id: str | None = None


class TicketFilters(FilterModel):
    __search_fields__ = ["event", "name", "email", "id"]
    __sort_fields__ = [
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


class BasketItem(BaseModel):
    ticket_type_id: str
    quantity: int = 1


class CreateBasket(BaseModel):
    name: str
    email: str | None = None
    items: list[BasketItem]
    promo_codes: list[str] = Field(default_factory=list)
    payment_method: str | None = None
    fiat_provider: str | None = None
    nostr_identifier: str | None = None
    refund_address: str | None = None


class BasketDiscount(BaseModel):
    code: str
    discount_percent: float | None = None
    discount_fixed: int | None = None
    amount_saved: float = 0


class PromoRequirement(BaseModel):
    """A recognised offer code that still needs more input before it applies.

    Drives the checkout's auto-prompt: the buyer types an offer code, this says
    a ticket id is also needed, and the checkout reveals that input.
    """

    code: str
    requires: str = "ticket_id"
    message: str | None = None


class PromoRejection(BaseModel):
    """Why a submitted token did not apply.

    Without this the checkout silently returns no discount, leaving the buyer
    with no idea whether the code was wrong, the ticket was wrong, or the offer
    was simply not applicable. ``reason`` is a stable code for the UI to
    translate; never parse ``message``.
    """

    code: str
    reason: str
    message: str | None = None


class BasketTotals(BaseModel):
    subtotal: float = 0
    discount: float = 0
    total: float = 0
    discounts_applied: list[BasketDiscount] = Field(default_factory=list)
    pending: list[PromoRequirement] = Field(default_factory=list)
    rejections: list[PromoRejection] = Field(default_factory=list)


class PromoValidateRequest(BaseModel):
    codes: list[str] = Field(default_factory=list)
    items: list[dict] = Field(default_factory=list)


class Basket(BaseModel):
    id: str
    event_id: str
    wallet: str
    email: str
    name: str
    promo_codes: list[str] = Field(default_factory=list)
    payment_method: str | None = None
    fiat_provider: str | None = None
    nostr_identifier: str | None = None
    refund_address: str | None = None
    satspay_charge_id: str | None = None
    paid: bool = False
    # Amount charged for this basket, in the event's currency, after discounts.
    # Recorded at creation and used to stamp per-ticket paid_value on payment.
    total: float | None = None
    time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BasketResponse(BaseModel):
    basket: Basket
    tickets: list[Ticket]
    totals: BasketTotals
    payment_request: TicketPaymentRequest | None = None
    event_name: str = ""
    event_image_url: str | None = None
    event_currency: str = "sat"
    event_fiat_currency: str = "GBP"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def sold_counts(tickets: list[Ticket]) -> dict[str, int]:
    """Committed seats per ticket type -- DERIVED, never read from the column.

    A seat is committed when its ticket is paid and neither refunded nor
    deactivated (an upgrade voids its source ticket, which frees the seat).
    ``TicketType.sold`` is incremented by ``set_ticket_paid``, but that returns
    early for a ticket which arrives already paid -- an import or a migration --
    so the stored column drifts low and every cap derived from it leaks.
    """
    counts: dict[str, int] = {}
    for ticket in tickets:
        if not ticket.paid or not ticket.ticket_type_id:
            continue
        extra = ticket.extra
        if extra is not None and (extra.refunded or extra.deactivated):
            continue
        counts[ticket.ticket_type_id] = counts.get(ticket.ticket_type_id, 0) + 1
    return counts


def get_active_ticket_types(
    ticket_types: list[TicketType], today: date | None = None
) -> list[TicketType]:
    current_day = today or datetime.utcnow().date()
    return [
        tt
        for tt in ticket_types
        if _parse_date(tt.available_from)
        <= current_day
        <= _parse_date(tt.available_to)
        and (tt.max_tickets == 0 or tt.sold < tt.max_tickets)
    ]


def sync_event_from_ticket_types(
    event: Event | CreateEvent, ticket_types: list[TicketType]
) -> Event | CreateEvent:
    if not ticket_types:
        return event

    event.amount_tickets = sum(tt.max_tickets for tt in ticket_types)
    event.price_per_ticket = ticket_types[0].price

    return event
