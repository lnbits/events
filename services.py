from __future__ import annotations

import asyncio
import smtplib
from asyncio.tasks import create_task
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Any

import httpx
from lnbits.core.models.users import UserNotifications
from lnbits.core.services.notifications import send_user_notification
from lnbits.helpers import is_valid_email_address, urlsafe_short_hash
from lnbits.settings import settings
from lnurl import execute
from loguru import logger

from .crud import (
    create_basket,
    create_ticket,
    get_basket,
    get_basket_tickets,
    get_event,
    get_event_tickets,
    get_ticket,
    get_ticket_type,
    get_ticket_types,
    purge_unpaid_tickets,
    update_basket,
    update_event,
    update_ticket,
    update_ticket_type,
)
from .models import (
    Basket,
    BasketDiscount,
    BasketTotals,
    CreateBasket,
    Event,
    EventExtra,
    NotificationDeliveryResult,
    PromoCode,
    Ticket,
    TicketResendResult,
    TicketType,
)


def _internal_host() -> str:
    return "127.0.0.1" if settings.host in ("0.0.0.0", "::") else settings.host


async def create_satspay_charge(api_key: str, data: dict) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url=f"http://{_internal_host()}:{settings.port}/satspay/api/v1/charge",
            headers={"X-API-KEY": api_key},
            json=data,
        )
        if resp.is_error:
            body = ""
            try:
                body = resp.json().get("detail", resp.text)
            except Exception:
                body = resp.text or "Unknown error"
            raise ValueError(f"SatsPay error: {body}")
        return resp.json()


async def get_satspay_charge(api_key: str, charge_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url=f"http://{_internal_host()}:{settings.port}/satspay/api/v1/charge/{charge_id}",
            headers={"X-API-KEY": api_key},
        )
        resp.raise_for_status()
        return resp.json()


def _effective_discount(promo, price: float) -> float:
    discount = 0
    if promo.discount_percent is not None:
        discount = price * promo.discount_percent / 100
    if promo.discount_fixed is not None:
        discount += promo.discount_fixed
    return min(discount, price)


def _promo_scope(promo) -> list:
    """Ticket-type ids a promo is restricted to (empty = basket-wide)."""
    return list(getattr(promo, "ticket_type_ids", None) or [])


def _apply_promo_codes(
    promos: list, type_subtotals: dict, subtotal: float
) -> tuple[float, list[BasketDiscount]]:
    """Apply promo codes to a basket.

    ``type_subtotals`` maps ticket_type_id -> value of that type in the basket.
    A promo scoped to specific ticket types discounts only against the value of
    those types; an unscoped promo discounts against the whole (remaining)
    basket. Stacking rule: ticket-type-scoped ("base") promos are applied
    first, each against its own base; any basket-wide promos then apply against
    what is left, so a combinable scoped code and a combinable basket code
    stack predictably.
    """
    discounts_applied: list[BasketDiscount] = []
    remaining_by_type: dict = {k: float(v) for k, v in (type_subtotals or {}).items()}
    remaining_total = float(subtotal)
    total_discount = 0.0

    def _base(promo) -> float:
        scope = _promo_scope(promo)
        if not scope:
            return max(0.0, remaining_total)
        total = 0.0
        for tid in scope:
            # Duplicate ids must not double-count.
            value = remaining_by_type.get(tid, 0.0)
            total += value
        return max(0.0, total)

    # Scoped promos first (each against its own base), then basket-wide ones.
    scoped = [p for p in promos if _promo_scope(p)]
    basket = [p for p in promos if not _promo_scope(p)]
    scoped.sort(key=lambda p: _effective_discount(p, _base(p)), reverse=True)
    basket.sort(key=lambda p: _effective_discount(p, _base(p)), reverse=True)

    for promo in scoped + basket:
        if not promo.active:
            continue
        if (promo.max_uses is not None
                and promo.max_uses > 0
                and promo.used_count >= promo.max_uses):
            continue
        scope = _promo_scope(promo)
        base = _base(promo)
        if base <= 0:
            continue
        # Never discount more than the value of the base the promo targets.
        discount_amount = min(_effective_discount(promo, base), base)
        if discount_amount <= 0:
            continue
        total_discount += discount_amount
        remaining_total -= discount_amount
        if scope:
            # Consume the discount from the targeted types, weighted by their
            # remaining share, so a later scoped promo on the same types cannot
            # discount value already discounted away.
            scope_remaining = sum(remaining_by_type.get(tid, 0.0) for tid in scope)
            for tid in scope:
                cur = remaining_by_type.get(tid, 0.0)
                share = (cur / scope_remaining) if scope_remaining > 0 else 0.0
                remaining_by_type[tid] = max(0.0, cur - discount_amount * share)
        discounts_applied.append(
            BasketDiscount(
                code=promo.code,
                discount_percent=promo.discount_percent,
                discount_fixed=promo.discount_fixed,
                amount_saved=discount_amount,
            )
        )
        if not promo.combinable:
            break

    return total_discount, discounts_applied


# ---------------------------------------------------------------------------
# Ticket-ID vouchers ("type": "ticket" promo codes)
#
# A ticket-type promo doesn't use a fixed code string. Instead the buyer
# submits an EXISTING tickets.id as the discount code; it is resolved against
# the tickets table at checkout. Single/multi-use is tracked PER SOURCE TICKET
# in the source ticket's TicketExtra (``ticket_id_voucher_redemptions``), not
# on the promo row, because the "code" is dynamic. A redemption is reserved
# ("pending") at checkout creation and only finalized on payment, so two
# concurrent checkouts can't both consume the last slot.
# ---------------------------------------------------------------------------
TICKET_VOUCHER_CODE = "TICKETID"
_VOUCHER_TTL_SECONDS = 24 * 3600  # matches the satspay charge time (1440 min)

# Per-event locks so concurrent checkouts race on reservation in one process.
_reservation_locks: dict[str, asyncio.Lock] = {}


def _reservation_lock(event_id: str) -> asyncio.Lock:
    if event_id not in _reservation_locks:
        _reservation_locks[event_id] = asyncio.Lock()
    return _reservation_locks[event_id]


def _find_ticket_voucher_promo(event: Event) -> PromoCode | None:
    for promo in event.extra.promo_codes:
        if promo.type == "ticket" and promo.active:
            return promo
    return None


async def _resolve_ticket_id_voucher(event: Event, ticket_id: str) -> Ticket | None:
    if not ticket_id:
        return None
    source = await get_ticket(ticket_id)
    if not source:
        return None
    if not source.paid or source.extra.deactivated:
        return None
    if source.event != event.id:
        return None
    return source


def _active_redemption_count(redemptions: list, now: datetime) -> int:
    count = 0
    for r in redemptions or []:
        status = r.get("status")
        if status == "completed":
            count += 1
            continue
        if status == "pending":
            expires_at = r.get("expires_at")
            if expires_at:
                try:
                    exp = datetime.fromisoformat(expires_at)
                except (TypeError, ValueError):
                    exp = None
                if exp is not None and exp > now:
                    count += 1
    return count


def _prune_expired_redemptions(redemptions: list, now: datetime) -> list:
    kept = []
    for r in redemptions or []:
        if r.get("status") == "pending":
            expires_at = r.get("expires_at")
            if expires_at:
                try:
                    exp = datetime.fromisoformat(expires_at)
                except (TypeError, ValueError):
                    exp = None
                if exp is not None and exp <= now:
                    continue  # expired pending reservation -> release slot
        kept.append(r)
    return kept


def _ticket_voucher_available(source: Ticket, promo: PromoCode, now: datetime) -> bool:
    count = _active_redemption_count(source.extra.ticket_id_voucher_redemptions, now)
    return count < (promo.redemptions_per_ticket or 1)


async def _reserve_ticket_voucher(
    event: Event, source_ticket_id: str, basket_id: str
) -> None:
    """Authoritative, concurrency-safe reservation of one voucher slot."""
    promo = _find_ticket_voucher_promo(event)
    if not promo:
        raise ValueError("Ticket-ID discount is not configured for this event.")
    source = await _resolve_ticket_id_voucher(event, source_ticket_id)
    if not source:
        raise ValueError("Invalid or ineligible ticket ID for discount.")
    now = datetime.now(timezone.utc)
    if not _ticket_voucher_available(source, promo, now):
        raise ValueError("This ticket has already been used for its discount.")
    redemptions = _prune_expired_redemptions(
        source.extra.ticket_id_voucher_redemptions, now
    )
    redemptions.append(
        {
            "basket_id": basket_id,
            "status": "pending",
            "time": now.isoformat(),
            "expires_at": (now + timedelta(seconds=_VOUCHER_TTL_SECONDS)).isoformat(),
        }
    )
    source.extra.ticket_id_voucher_redemptions = redemptions
    await update_ticket(source)


async def _finalize_ticket_voucher(source: Ticket, basket_id: str) -> None:
    redemptions = list(source.extra.ticket_id_voucher_redemptions or [])
    changed = False
    for r in redemptions:
        if r.get("basket_id") == basket_id and r.get("status") == "pending":
            r["status"] = "completed"
            r.pop("expires_at", None)
            changed = True
    if changed:
        source.extra.ticket_id_voucher_redemptions = redemptions
        await update_ticket(source)


async def _increment_promo_uses(event: Event, promo_codes: list[BasketDiscount]) -> None:
    if not promo_codes:
        return
    applied_codes = {d.code for d in promo_codes}
    modified = False
    for promo in event.extra.promo_codes:
        if promo.code in applied_codes:
            promo.used_count += 1
            modified = True
    if modified:
        await update_event(event)


async def calculate_basket_total(
    event: Event,
    items: list[dict],
    promo_codes: list[str],
    *,
    allow_consumed: bool = False,
) -> BasketTotals:
    ticket_types = await get_ticket_types(event.id)
    types_by_id = {tt.id: tt for tt in ticket_types}

    subtotal = 0
    type_subtotals: dict = {}
    for item in items:
        tt = types_by_id.get(item["ticket_type_id"])
        if not tt:
            continue
        line_total = float(tt.price) * item.get("quantity", 1)
        subtotal += line_total
        tid = item["ticket_type_id"]
        type_subtotals[tid] = type_subtotals.get(tid, 0.0) + line_total

    if event.currency.lower() in ("sat", "sats"):
        subtotal = int(subtotal)

    submitted = [c.upper() for c in promo_codes]
    promos = [p for p in event.extra.promo_codes if p.code in submitted]

    # Resolve ticket-ID vouchers: a submitted code that is not a configured
    # promo string is treated as an existing ticket id. Only allowed for a
    # single-ticket purchase (basket of exactly one ticket). Ticket ids are
    # case-sensitive, so resolve against the RAW submitted codes, not the
    # upper-cased forms used for static promo matching.
    single_ticket = sum(item.get("quantity", 1) for item in items) == 1
    voucher_promo = _find_ticket_voucher_promo(event)
    if single_ticket and voucher_promo:
        matched_codes = {p.code for p in promos}
        for code in promo_codes:
            if code.upper() in matched_codes:
                continue
            source = await _resolve_ticket_id_voucher(event, code)
            if not source:
                continue
            # allow_consumed is used for re-displaying an already-created/
            # paid basket: enforcement happens at checkout creation, so an
            # overview must show the applied voucher even once the source
            # ticket's redemption slots are consumed.
            if not allow_consumed and not _ticket_voucher_available(
                source, voucher_promo, datetime.now(timezone.utc)
            ):
                continue
            promos.append(
                # construct() bypasses the code-uppercasing validator, keeping
                # the source ticket id's original case (it is a PK lookup key).
                PromoCode.construct(
                    code=code,
                    type="ticket",
                    discount_percent=voucher_promo.discount_percent,
                    discount_fixed=voucher_promo.discount_fixed,
                    active=True,
                    combinable=False,
                    max_uses=None,
                    used_count=0,
                )
            )

    # Ordering (scoped bases first, then basket-wide) is handled inside
    # _apply_promo_codes, which needs per-ticket-type bases to compute it.
    total_discount, discounts_applied = _apply_promo_codes(
        promos, type_subtotals, subtotal
    )
    total = max(0, subtotal - total_discount)

    if event.currency.lower() in ("sat", "sats"):
        subtotal = int(subtotal)
        total_discount = int(total_discount)
        total = int(total)
    else:
        subtotal = round(subtotal, 2)
        total_discount = round(total_discount, 2)
        total = round(total, 2)

    return BasketTotals(
        subtotal=subtotal,
        discount=total_discount,
        total=total,
        discounts_applied=discounts_applied,
    )


async def create_basket_with_charge(
    event: Event,
    data: CreateBasket,
    wallet_inkey: str,
    base_url: str,
) -> tuple[Basket, list[Ticket], BasketTotals, dict | None]:
    today = __import__("datetime").datetime.utcnow().date()
    from .models import _parse_date

    ticket_types = await get_ticket_types(event.id)
    active_types = [
        tt for tt in ticket_types
        if _parse_date(tt.available_from) <= today <= _parse_date(tt.available_to)
        and (tt.max_tickets == 0 or tt.sold < tt.max_tickets)
    ]
    active_ids = {tt.id for tt in active_types}

    for item in data.items:
        if item.ticket_type_id not in active_ids:
            raise ValueError(f"Ticket type {item.ticket_type_id} is not available.")
        tt = next(tt for tt in active_types if tt.id == item.ticket_type_id)
        remaining = tt.max_tickets - tt.sold if tt.max_tickets > 0 else float("inf")
        if item.quantity > remaining:
            raise ValueError(
                f"Only {remaining} tickets available for '{tt.name}'."
            )

    totals = await calculate_basket_total(
        event,
        [{"ticket_type_id": i.ticket_type_id, "quantity": i.quantity} for i in data.items],
        data.promo_codes,
    )

    basket_id = urlsafe_short_hash()
    # Keep the RAW submitted codes so ticket-ID vouchers (case-sensitive)
    # survive into basket.promo_codes. Static-code matching upper-cases at the
    # point of comparison.
    promo_code_strings = list(data.promo_codes)

    # Authoritatively reserve ticket-ID voucher redemptions on their source
    # tickets. This is the write that closes the single-use race: it happens
    # under a per-event lock, before any charge is created, so two concurrent
    # checkouts can't both claim the last available slot.
    if sum(i.quantity for i in data.items) == 1:
        static_codes = {p.code for p in event.extra.promo_codes}
        voucher_discounts = [
            d
            for d in totals.discounts_applied
            if d.code not in static_codes
        ]
        if voucher_discounts:
            async with _reservation_lock(event.id):
                for discount in voucher_discounts:
                    await _reserve_ticket_voucher(event, discount.code, basket_id)

    basket = Basket(
        id=basket_id,
        event_id=event.id,
        wallet=event.wallet,
        email=data.email or '',
        name=data.name,
        promo_codes=promo_code_strings,
        payment_method=data.payment_method,
        fiat_provider=data.fiat_provider,
        nostr_identifier=data.nostr_identifier,
        refund_address=data.refund_address,
    )

    charge = None
    tickets: list[Ticket] = []

    if totals.total > 0:
        methods = event.extra.payment_methods or []

        internal_base = f"http://{_internal_host()}:{settings.port}"
        webhook_url = f"{internal_base}/events/api/v1/baskets/{basket_id}/satspay-webhook"
        complete_url = f"{base_url}/events/basket/{basket_id}"

        is_fiat_currency = event.currency and event.currency.lower() not in ("sat", "sats")

        base_data = {
            "description": f"Tickets for {event.name}",
            "name": data.name or "",
            "webhook": webhook_url,
            "completelink": complete_url,
            "completelinktext": "View your tickets",
            "time": 1440,
        }
        if is_fiat_currency:
            base_data["currency"] = event.currency.lower()
            base_data["currency_amount"] = float(totals.total)
        else:
            base_data["amount"] = totals.total

        charge_data = dict(base_data)
        if "ln" in methods:
            charge_data["lnbitswallet"] = event.extra.ln_wallet_id or event.wallet
        if "onchain" in methods:
            charge_data["onchainwallet"] = event.extra.onchain_wallet_id
        if "fiat" in methods:
            charge_data["fiat_provider"] = data.fiat_provider

        charge = None
        last_error = None
        tried_methods = list(methods)

        while tried_methods and charge is None:
            try:
                charge = await create_satspay_charge(
                    api_key=wallet_inkey,
                    data=charge_data,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(f"SatsPay charge failed with methods {tried_methods}: {exc}")
                failed = tried_methods.pop(0)
                charge_data = dict(base_data)
                if "ln" in tried_methods:
                    charge_data["lnbitswallet"] = event.extra.ln_wallet_id or event.wallet
                if "onchain" in tried_methods:
                    charge_data["onchainwallet"] = event.extra.onchain_wallet_id
                if "fiat" in tried_methods:
                    charge_data["fiat_provider"] = data.fiat_provider

        if charge is None:
            raise ValueError(
                f"Could not create payment for any enabled method. "
                f"Last error: {last_error}"
            )

        basket.satspay_charge_id = charge["id"]

    await create_basket_from_model(basket)

    for item in data.items:
        tt = next(tt for tt in ticket_types if tt.id == item.ticket_type_id)
        for _ in range(item.quantity):
            ticket_id = urlsafe_short_hash()
            ticket = await create_ticket(
                payment_hash=ticket_id,
                wallet=event.wallet,
                event=event.id,
                name=data.name,
                email=data.email or '',
                extra={
                    "ticket_type_id": tt.id,
                    "ticket_wave_title": tt.name,
                    "refund_address": data.refund_address,
                    "nostr_identifier": data.nostr_identifier,
                    "ticket_base_url": base_url,
                    "sats_paid": totals.total,
                    "satspay_charge_id": basket.satspay_charge_id,
                    "applied_promo_code": ",".join(promo_code_strings) if promo_code_strings else None,
                },
                ticket_type_id=tt.id,
                basket_id=basket_id,
            )
            tickets.append(ticket)

    if totals.total == 0:
        await _activate_basket_tickets(basket, tickets, event)

    return basket, tickets, totals, charge


async def create_basket_from_model(basket: Basket) -> Basket:
    return await create_basket(basket)


async def _activate_basket_tickets(
    basket: Basket, tickets: list[Ticket], event: Event
) -> None:
    for ticket in tickets:
        await set_ticket_paid(ticket)
    basket.paid = True
    await update_basket(basket)
    await _increment_promo_uses_from_basket(event, basket)
    # Finalize ticket-ID voucher redemptions (pending -> completed) now that
    # this basket is actually paid.
    static_codes = {p.code for p in event.extra.promo_codes}
    for code in basket.promo_codes or []:
        if code.upper() in static_codes:
            continue
        source = await _resolve_ticket_id_voucher(event, code)
        if source:
            await _finalize_ticket_voucher(source, basket.id)
    _send_basket_notifications_in_background(basket, tickets, event)
    if event.admin_email:
        create_task(_send_admin_sale_notification(event, basket, tickets))


async def handle_basket_payment(
    basket_id: str, wallet_inkey: str
) -> dict | None:
    basket = await get_basket(basket_id)
    if not basket:
        logger.warning(f"Basket {basket_id} not found.")
        return None
    if basket.paid:
        logger.warning(f"Basket {basket_id} already paid.")
        return None
    if not basket.satspay_charge_id:
        raise ValueError("Basket has no SatsPay charge.")

    charge = await get_satspay_charge(wallet_inkey, basket.satspay_charge_id)
    if not charge.get("paid"):
        logger.warning(f"Charge {basket.satspay_charge_id} not paid.")
        return charge

    event = await get_event(basket.event_id)
    if not event:
        raise ValueError("Event not found for basket.")

    tickets = await get_basket_tickets(basket_id)
    await _activate_basket_tickets(basket, tickets, event)

    return charge


# ---------------------------------------------------------------------------
# Email formatting helpers
# ---------------------------------------------------------------------------

_CURRENCY_SYMBOLS = {"GBP": "£", "EUR": "€", "USD": "$", "JPY": "¥"}


def _currency_symbol(currency: str) -> str:
    return _CURRENCY_SYMBOLS.get(currency.upper(), currency + " ")


def _format_price(event: Event, amount: float) -> str:
    if event.currency.lower() in ("sat", "sats"):
        return f"{int(amount)} sats"
    symbol = _currency_symbol(event.fiat_currency or event.currency)
    return f"{symbol}{amount:.2f}"


def _format_event_dates(event: Event) -> str:
    try:
        start = datetime.strptime(event.event_start_date, "%Y-%m-%d")
        end = datetime.strptime(event.event_end_date, "%Y-%m-%d")
        if start == end:
            return start.strftime("%A, %d %B %Y")
        if start.year == end.year and start.month == end.month:
            return f"{start.strftime('%A, %d')} – {end.strftime('%d %B %Y')}"
        if start.year == end.year:
            return f"{start.strftime('%A, %d %B')} – {end.strftime('%A, %d %B %Y')}"
        return f"{start.strftime('%d %B %Y')} – {end.strftime('%d %B %Y')}"
    except (ValueError, TypeError):
        return f"{event.event_start_date} – {event.event_end_date}"


def _ticket_type_name(ticket: Ticket, tt_map: dict) -> str:
    if ticket.ticket_type_id and ticket.ticket_type_id in tt_map:
        return tt_map[ticket.ticket_type_id].name
    return "General Admission"


def _ticket_type_price(ticket: Ticket, tt_map: dict) -> float | None:
    if ticket.ticket_type_id and ticket.ticket_type_id in tt_map:
        return float(tt_map[ticket.ticket_type_id].price)
    return None


def _display_name(name: str | None) -> str:
    return name if name else "Anon"


def _grouped_ticket_types(tickets: list[Ticket], tt_map: dict) -> list[tuple[str, int, float]]:
    counts: dict[str, dict] = {}
    for t in tickets:
        tt_name = _ticket_type_name(t, tt_map)
        if tt_name not in counts:
            price = _ticket_type_price(t, tt_map) or 0
            counts[tt_name] = {"qty": 0, "price": price}
        counts[tt_name]["qty"] += 1
    return [(name, d["qty"], d["price"]) for name, d in counts.items()]


# ---------------------------------------------------------------------------
# HTML email template builders
# ---------------------------------------------------------------------------

_EMAIL_BASE_STYLE = (
    "margin:0;padding:0;background:#f0f0f0;"
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
    "Helvetica,Arial,sans-serif;"
)
_EMAIL_WRAPPER_STYLE = "background:#f0f0f0;padding:24px 12px;"
_EMAIL_CARD_STYLE = (
    "background:#ffffff;border-radius:10px;overflow:hidden;"
    "max-width:600px;margin:0 auto;"
    "box-shadow:0 2px 8px rgba(0,0,0,0.08);"
)
_EMAIL_BANNER_STYLE = (
    "display:block;width:100%;max-height:220px;object-fit:cover;"
)
_EMAIL_HEADER_STYLE = (
    "background:#161b22;padding:32px 40px;text-align:center;"
)
_EMAIL_H1_STYLE = "margin:0 0 6px 0;font-size:24px;color:#ffffff;font-weight:700;"
_EMAIL_H2_STYLE = "margin:0 0 4px 0;font-size:18px;color:#161b22;font-weight:600;"
_EMAIL_DATE_STYLE = "margin:0;font-size:14px;color:#8b949e;"
_EMAIL_SECTION_STYLE = "padding:0 40px;"
_EMAIL_BODY_STYLE = "margin:0 0 20px 0;font-size:15px;color:#1f2328;line-height:1.6;"
_EMAIL_CARD_INNER = (
    "background:#f6f8fa;border:1px solid #d0d7de;border-radius:8px;"
    "padding:20px;margin-bottom:16px;"
)
_EMAIL_LABEL_STYLE = "margin:0 0 2px 0;font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:0.5px;"
_EMAIL_VALUE_STYLE = "margin:0 0 12px 0;font-size:15px;color:#1f2328;"
_EMAIL_BTN_STYLE = (
    "display:inline-block;background:#0969da;color:#ffffff;"
    "text-decoration:none;font-size:14px;font-weight:600;"
    "padding:10px 28px;border-radius:6px;"
)
_EMAIL_BTN_OUTLINE_STYLE = (
    "display:inline-block;background:transparent;color:#0969da;"
    "text-decoration:none;font-size:14px;font-weight:600;"
    "padding:10px 24px;border-radius:6px;border:1px solid #0969da;"
)
_EMAIL_FOOTER_STYLE = (
    "background:#f6f8fa;padding:24px 40px;text-align:center;"
    "border-top:1px solid #d0d7de;"
)
_EMAIL_FOOTER_P_STYLE = "margin:0;font-size:12px;color:#8b949e;line-height:1.5;"


def _email_header_html(event: Event) -> str:
    if event.banner:
        return (
            f'<tr><td style="padding:0;">'
            f'<img src="{escape(event.banner, quote=True)}" '
            f'alt="{escape(event.name, quote=True)}" '
            f'style="{_EMAIL_BANNER_STYLE}" />'
            f'</td></tr>'
            f'<tr><td style="{_EMAIL_HEADER_STYLE}">'
            f'<h1 style="{_EMAIL_H1_STYLE}">{escape(event.name)}</h1>'
            f'<p style="{_EMAIL_DATE_STYLE}">{escape(_format_event_dates(event))}</p>'
            f'</td></tr>'
        )
    return (
        f'<tr><td style="{_EMAIL_HEADER_STYLE}">'
        f'<h1 style="{_EMAIL_H1_STYLE}">{escape(event.name)}</h1>'
        f'<p style="{_EMAIL_DATE_STYLE}">{escape(_format_event_dates(event))}</p>'
        f'</td></tr>'
    )


def _email_footer_html() -> str:
    base = escape(settings.lnbits_baseurl or "")
    return (
        f'<tr><td style="{_EMAIL_FOOTER_STYLE}">'
        f'<p style="{_EMAIL_FOOTER_P_STYLE}">'
        f'Tickets powered by LNbits'
        f"</p>"
        f'<p style="{_EMAIL_FOOTER_P_STYLE}">'
        f'<a href="{base}" style="color:#0969da;text-decoration:none;">{base}</a>'
        f"</p>"
        f"</td></tr>"
    )


def _ticket_row_html(ticket: Ticket, tt_map: dict) -> str:
    tt_name = escape(_ticket_type_name(ticket, tt_map))
    url = escape(_ticket_url(ticket), quote=True)
    return (
        f'<div style="{_EMAIL_CARD_INNER}">'
        f'<p style="margin:0 0 12px 0;font-size:16px;font-weight:600;color:#161b22;">{tt_name}</p>'
        f'<a href="{url}" style="{_EMAIL_BTN_STYLE}">Open ticket</a>'
        f'</div>'
    )


def _order_summary_html(
    event: Event,
    basket: Basket,
    tickets: list[Ticket],
    tt_map: dict,
    base_url: str,
) -> str:
    buyer = escape(_display_name(basket.name))
    buyer_email = escape(basket.email) if basket.email else "—"
    basket_url = escape(f"{base_url}/events/basket/{basket.id}", quote=True)
    count = len(tickets)

    total = 0.0
    for t in tickets:
        p = _ticket_type_price(t, tt_map)
        if p is not None:
            total += p
    total_str = escape(_format_price(event, total)) if total > 0 else ""

    rows = (
        f'<p style="{_EMAIL_LABEL_STYLE}">Order ID</p>'
        f'<p style="{_EMAIL_VALUE_STYLE}">'
        f'<a href="{basket_url}" style="color:#0969da;text-decoration:none;font-weight:600;">{escape(basket.id)}</a>'
        f'</p>'
        f'<p style="{_EMAIL_LABEL_STYLE}">Buyer</p>'
        f'<p style="{_EMAIL_VALUE_STYLE}">{buyer} &lt;{buyer_email}&gt;</p>'
        f'<p style="{_EMAIL_LABEL_STYLE}">Tickets</p>'
        f'<p style="{_EMAIL_VALUE_STYLE}">{count}</p>'
    )
    if total_str:
        rows += (
            f'<p style="{_EMAIL_LABEL_STYLE}">Total paid</p>'
            f'<p style="margin:0;font-size:18px;font-weight:700;color:#1f2328;">{total_str}</p>'
        )

    return (
        f'<div style="background:#ddf4ff;border:1px solid #0969da;border-radius:8px;padding:20px;">'
        f'{rows}'
        f'</div>'
    )


def _render_ticket_email_html(
    event: Event,
    tickets: list[Ticket],
    tt_map: dict,
    body_text: str,
    basket: Basket | None = None,
    base_url: str = "",
) -> str:
    header = _email_header_html(event)

    body_html = (
        f'<tr><td style="{_EMAIL_SECTION_STYLE}padding-top:28px;">'
        f'<p style="{_EMAIL_BODY_STYLE}">{escape(body_text).replace(chr(10), "<br />")}</p>'
        f'</td></tr>'
    )

    tickets_label = "Your ticket" if len(tickets) == 1 else "Your tickets"
    ticket_rows = "".join(_ticket_row_html(t, tt_map) for t in tickets)
    tickets_html = (
        f'<tr><td style="{_EMAIL_SECTION_STYLE}padding-top:8px;">'
        f'<h2 style="{_EMAIL_H2_STYLE}">{tickets_label}</h2>'
        f'<div style="margin-top:12px;">{ticket_rows}</div>'
        f'</td></tr>'
    )

    basket_link_html = ""
    if basket and base_url:
        basket_url = escape(f"{base_url}/events/basket/{basket.id}", quote=True)
        basket_link_html = (
            f'<tr><td style="{_EMAIL_SECTION_STYLE}padding-top:0;">'
            f'<div style="margin-top:8px;">'
            f'<a href="{basket_url}" style="{_EMAIL_BTN_OUTLINE_STYLE}">View basket</a>'
            f'</div>'
            f'</td></tr>'
        )

    summary_html = ""
    if basket and base_url:
        summary_html = (
            f'<tr><td style="{_EMAIL_SECTION_STYLE}padding-top:24px;padding-bottom:28px;">'
            f'<h2 style="{_EMAIL_H2_STYLE}">Order summary</h2>'
            f'<div style="margin-top:12px;">'
            f'{_order_summary_html(event, basket, tickets, tt_map, base_url)}'
            f'</div>'
            f'</td></tr>'
        )
    else:
        summary_html = f'<tr><td style="height:20px;"></td></tr>'

    footer = _email_footer_html()

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '</head><body style="' + _EMAIL_BASE_STYLE + '">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="' + _EMAIL_WRAPPER_STYLE + '">'
        '<tr><td>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="' + _EMAIL_CARD_STYLE + '">'
        + header +
        body_html +
        tickets_html +
        basket_link_html +
        summary_html +
        footer +
        '</table></td></tr></table></body></html>'
    )


def _render_admin_email_html(
    event: Event,
    basket: Basket,
    tickets: list[Ticket],
    tt_map: dict,
    base_url: str,
) -> str:
    header = _email_header_html(event)

    count = len(tickets)
    total = 0.0
    for t in tickets:
        p = _ticket_type_price(t, tt_map)
        if p is not None:
            total += p
    total_str = escape(_format_price(event, total)) if total > 0 else ""

    buyer = escape(_display_name(basket.name))
    buyer_email = escape(basket.email) if basket.email else "—"
    basket_url = escape(f"{base_url}/events/basket/{basket.id}", quote=True)

    summary_html = (
        f'<tr><td style="{_EMAIL_SECTION_STYLE}padding-top:8px;">'
        f'<div style="background:#ddf4ff;border:1px solid #0969da;border-radius:8px;padding:20px;">'
        f'<p style="{_EMAIL_LABEL_STYLE}">Order ID</p>'
        f'<p style="{_EMAIL_VALUE_STYLE}">'
        f'<a href="{basket_url}" style="color:#0969da;text-decoration:none;font-weight:600;">{escape(basket.id)}</a>'
        f'</p>'
        f'<p style="{_EMAIL_LABEL_STYLE}">Buyer</p>'
        f'<p style="{_EMAIL_VALUE_STYLE}">{buyer} &lt;{buyer_email}&gt;</p>'
        f'<p style="{_EMAIL_LABEL_STYLE}">Tickets sold</p>'
        f'<p style="{_EMAIL_VALUE_STYLE}">{count}</p>'
        f'<p style="{_EMAIL_LABEL_STYLE}">Total</p>'
        f'<p style="margin:0;font-size:18px;font-weight:700;color:#1f2328;">{total_str}</p>'
        f'</div>'
        f'</td></tr>'
    )

    grouped = _grouped_ticket_types(tickets, tt_map)
    ticket_rows = ""
    for tt_name, qty, price in grouped:
        price_str = escape(_format_price(event, price * qty)) if price > 0 else ""
        ticket_rows += (
            f'<tr>'
            f'<td style="padding:10px 0;border-bottom:1px solid #d0d7de;">'
            f'<p style="margin:0;font-weight:600;color:#161b22;">{escape(tt_name)}</p>'
            f'</td>'
            f'<td style="padding:10px 0;border-bottom:1px solid #d0d7de;text-align:right;vertical-align:top;">'
            f'<p style="margin:0;font-size:15px;color:#1f2328;">×{qty}</p>'
            f'</td>'
            f'<td style="padding:10px 0;border-bottom:1px solid #d0d7de;text-align:right;vertical-align:top;">'
            f'<p style="margin:0;font-size:14px;font-weight:600;color:#1f2328;">{price_str}</p>'
            f'</td>'
            f'</tr>'
        )

    tickets_html = (
        f'<tr><td style="{_EMAIL_SECTION_STYLE}padding-top:24px;padding-bottom:28px;">'
        f'<h2 style="{_EMAIL_H2_STYLE}">Tickets in this sale</h2>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;">'
        f'<thead><tr>'
        f'<td style="{_EMAIL_LABEL_STYLE}padding-bottom:8px;">Ticket type</td>'
        f'<td style="{_EMAIL_LABEL_STYLE}padding-bottom:8px;text-align:right;">Qty</td>'
        f'<td style="{_EMAIL_LABEL_STYLE}padding-bottom:8px;text-align:right;">Total</td>'
        f'</tr></thead>'
        f'<tbody>{ticket_rows}</tbody>'
        f'</table>'
        f'</td></tr>'
    )

    body_html = (
        f'<tr><td style="{_EMAIL_SECTION_STYLE}padding-top:28px;">'
        f'<h2 style="{_EMAIL_H2_STYLE}">New ticket sale</h2>'
        f'<p style="{_EMAIL_BODY_STYLE}">'
        f'{count} ticket(s) were just sold for '
        f'<strong>{escape(event.name)}</strong>.</p>'
        f'</td></tr>'
    )

    footer = _email_footer_html()

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '</head><body style="' + _EMAIL_BASE_STYLE + '">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="' + _EMAIL_WRAPPER_STYLE + '">'
        '<tr><td>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="' + _EMAIL_CARD_STYLE + '">'
        + header +
        body_html +
        summary_html +
        tickets_html +
        footer +
        '</table></td></tr></table></body></html>'
    )


# ---------------------------------------------------------------------------
# Notification senders
# ---------------------------------------------------------------------------

async def _send_admin_sale_notification(
    event: Event, basket: Basket, tickets: list[Ticket]
) -> None:
    if not event.admin_email or not settings.lnbits_email_notifications_enabled:
        return

    tt_map: dict[str, TicketType] = {}
    tt_ids = {t.ticket_type_id for t in tickets if t.ticket_type_id}
    for ttid in tt_ids:
        tt = await get_ticket_type(ttid)
        if tt:
            tt_map[tt.id] = tt

    base_url = _resolve_base_url(tickets)
    count = len(tickets)

    grouped = _grouped_ticket_types(tickets, tt_map)
    ticket_details = "\n".join(
        f"- {name} ×{qty}"
        + (f" — {_format_price(event, price * qty)}" if price > 0 else "")
        for name, qty, price in grouped
    )
    total = sum(price * qty for _, qty, price in grouped)
    total_str = _format_price(event, total) if total > 0 else ""

    basket_url = f"{base_url}/events/basket/{basket.id}"
    text_message = (
        f"New ticket sale for '{event.name}'\n"
        f"{_format_event_dates(event)}\n\n"
        f"Order ID: {basket.id}\n"
        f"View basket: {basket_url}\n"
        f"Buyer: {_display_name(basket.name)} ({basket.email or '—'})\n"
        f"Tickets: {count}\n"
        f"Total: {total_str}\n\n"
        f"{ticket_details}"
    )
    subject = f"New sale: {count} ticket(s) for '{event.name}'"
    html_message = _render_admin_email_html(event, basket, tickets, tt_map, base_url)

    try:
        await _send_ticket_email_notification(
            [event.admin_email], text_message, subject, html_message
        )
    except Exception as exc:
        logger.warning(f"Failed to send admin notification: {exc}")


async def _increment_promo_uses_from_basket(
    event: Event, basket: Basket
) -> None:
    if not basket.promo_codes:
        return
    applied_codes = {c.upper() for c in basket.promo_codes}
    modified = False
    for promo in event.extra.promo_codes:
        if promo.code in applied_codes:
            promo.used_count += 1
            modified = True
    if modified:
        await update_event(event)


async def toggle_ticket_deactivation(ticket: Ticket) -> Ticket:
    ticket.extra.deactivated = not ticket.extra.deactivated
    await update_ticket(ticket)
    return ticket


async def set_ticket_paid(ticket: Ticket) -> Ticket:
    if ticket.paid:
        return ticket

    ticket.paid = True
    await update_ticket(ticket)

    event = await get_event(ticket.event)
    assert event, "Couldn't get event from ticket being paid"
    event.sold += 1

    if ticket.ticket_type_id:
        ticket_type = await get_ticket_type(ticket.ticket_type_id)
        if ticket_type:
            ticket_type.sold += 1
            await update_ticket_type(ticket_type)

    await update_event(event)

    return ticket


async def send_bulk_ticket_emails(
    event_id: str, base_url: str
) -> list[TicketResendResult]:
    tickets = await get_event_tickets(event_id)
    results: list[TicketResendResult] = []
    for ticket in tickets:
        if not ticket.paid:
            continue
        try:
            result = await resend_ticket_email_notification(
                ticket, base_url.rstrip("/")
            )
            results.append(result)
        except Exception as exc:
            logger.warning(f"Failed to resend ticket {ticket.id}: {exc}")
            results.append(
                TicketResendResult(
                    ticket=ticket,
                    email=NotificationDeliveryResult(
                        attempted=True, sent=False, error=str(exc)
                    ),
                )
            )
    return results


async def send_bulk_message(
    event_id: str, subject: str, message: str
) -> list[dict]:
    tickets = await get_event_tickets(event_id)
    results: list[dict] = []
    for ticket in tickets:
        if not ticket.email or not ticket.paid:
            continue
        try:
            await _send_ticket_email_notification(
                [ticket.email], message, subject
            )
            results.append({"ticket_id": ticket.id, "sent": True})
        except Exception as exc:
            logger.warning(f"Failed to send message for ticket {ticket.id}: {exc}")
            results.append(
                {"ticket_id": ticket.id, "sent": False, "error": str(exc)}
            )
    return results


def send_ticket_notification_in_background(ticket: Ticket) -> None:
    create_task(_send_ticket_notification(ticket))


def _send_basket_notifications_in_background(
    basket: Basket, tickets: list[Ticket], event: Event
) -> None:
    create_task(_send_basket_ticket_notifications(basket, tickets, event))


async def _send_basket_ticket_notifications(
    basket: Basket, tickets: list[Ticket], event: Event
) -> None:
    if not event.extra.email_notifications:
        return
    if not settings.lnbits_email_notifications_enabled:
        return

    tt_map = await _build_tt_map(tickets)
    base_url = _resolve_base_url(tickets)

    by_email: dict[str, list[Ticket]] = {}
    for ticket in tickets:
        if ticket.email:
            by_email.setdefault(ticket.email, []).append(ticket)

    for email, email_tickets in by_email.items():
        subject, text_message, html_message = _build_ticket_email(
            event, email_tickets, tt_map, basket, base_url
        )

        try:
            await _send_ticket_email_notification(
                [email], text_message, subject, html_message
            )
            for t in email_tickets:
                t.extra.email_notification_sent = True
        except Exception as exc:
            logger.warning(f"Failed to email tickets to {email}: {exc}")


async def _send_ticket_notification(ticket: Ticket) -> None:
    event = await get_event(ticket.event)
    if not event:
        logger.warning(f"Event {ticket.event} not found for ticket notification.")
        return

    await _deliver_ticket_notifications(ticket, event)


async def resend_ticket_email_notification(
    ticket: Ticket, base_url: str | None = None
) -> TicketResendResult:
    event = await get_event(ticket.event)
    if not event:
        raise ValueError("Event does not exist.")
    if not settings.lnbits_email_notifications_enabled:
        raise ValueError("Email notifications are not enabled.")
    if not ticket.email:
        raise ValueError("Ticket does not have an email address.")
    if base_url:
        ticket.extra.ticket_base_url = base_url.rstrip("/")

    return await _deliver_ticket_notifications(ticket, event)


async def _build_tt_map(tickets: list[Ticket]) -> dict[str, TicketType]:
    tt_map: dict[str, TicketType] = {}
    tt_ids = {t.ticket_type_id for t in tickets if t.ticket_type_id}
    for ttid in tt_ids:
        tt = await get_ticket_type(ttid)
        if tt:
            tt_map[tt.id] = tt
    return tt_map


def _resolve_base_url(tickets: list[Ticket]) -> str:
    for t in tickets:
        if t.extra.ticket_base_url:
            return t.extra.ticket_base_url.rstrip("/")
    return (settings.lnbits_baseurl or "").rstrip("/")


def _basket_url(basket: Basket, base_url: str) -> str:
    return f"{base_url}/events/basket/{basket.id}"


def _build_ticket_email(
    event: Event,
    tickets: list[Ticket],
    tt_map: dict,
    basket: Basket | None,
    base_url: str,
) -> tuple[str, str, str]:
    subject = (
        event.extra.notification_subject.strip()
        or (f"Your ticket for '{event.name}' is ready"
            if len(tickets) == 1
            else f"Your tickets for '{event.name}' are ready")
    )
    body = (
        event.extra.notification_body.strip()
        or (f"Your ticket for '{event.name}' is ready."
            if len(tickets) == 1
            else f"Your tickets for '{event.name}' are ready.")
    )

    ticket_lines = "\n".join(
        f"- {_ticket_type_name(t, tt_map)}"
        f"\n  Open ticket: {_ticket_url(t)}"
        for t in tickets
    )

    text_message = (
        f"{body}\n\n"
        f"{event.name}\n"
        f"{_format_event_dates(event)}\n\n"
        f"{ticket_lines}\n"
    )

    if basket:
        text_message += f"\nView basket: {_basket_url(basket, base_url)}\n"
        text_message += f"Order ID: {basket.id}\n"
        total = sum(_ticket_type_price(t, tt_map) or 0 for t in tickets)
        if total > 0:
            text_message += f"Total: {_format_price(event, total)}\n"

    html_message = _render_ticket_email_html(
        event, tickets, tt_map, body, basket=basket, base_url=base_url
    )

    return subject, text_message, html_message


def _supports_nostr_delivery(identifier: str | None) -> bool:
    return bool(identifier and "@" in identifier)


async def _deliver_ticket_notifications(
    ticket: Ticket, event: Event
) -> TicketResendResult:
    tt_map = await _build_tt_map([ticket])
    base_url = _resolve_base_url([ticket])
    basket: Basket | None = None
    if ticket.basket_id:
        basket = await get_basket(ticket.basket_id)

    subject, text_message, html_message = _build_ticket_email(
        event, [ticket], tt_map, basket, base_url
    )

    updated = False
    result = TicketResendResult(
        ticket=ticket,
        email=NotificationDeliveryResult(
            attempted=bool(
                event.extra.email_notifications
                and settings.lnbits_email_notifications_enabled
                and ticket.email
            )
        ),
        nostr=NotificationDeliveryResult(
            attempted=bool(
                event.extra.nostr_notifications
                and settings.is_nostr_notifications_configured()
                and ticket.extra.nostr_identifier
            )
        ),
    )

    if result.email.attempted:
        try:
            await _send_ticket_email_notification(
                [ticket.email], text_message, subject, html_message
            )
            ticket.extra.email_notification_sent = True
            result.email.sent = True
            updated = True
        except Exception as exc:
            logger.warning(f"Failed to email ticket {ticket.id}: {exc}")
            result.email.error = str(exc)

    if result.nostr.attempted and not _supports_nostr_delivery(
        ticket.extra.nostr_identifier
    ):
        result.nostr.error = "Only NIP-05 Nostr identifiers are supported."
    elif result.nostr.attempted:
        try:
            identifier = ticket.extra.nostr_identifier
            assert identifier is not None
            await _send_nostr_ticket_notification(identifier, text_message)
            ticket.extra.nostr_notification_sent = True
            result.nostr.sent = True
            updated = True
        except Exception as exc:
            logger.warning(f"Failed to send nostr DM for ticket {ticket.id}: {exc}")
            result.nostr.error = str(exc)

    if updated:
        result.ticket = await update_ticket(ticket)
    return result


async def _send_nostr_ticket_notification(identifier: str, message: str) -> None:
    await send_user_notification(
        UserNotifications(nostr_identifier=identifier),
        message,
        "text_message",
    )


async def _send_ticket_email_notification(
    to_emails: list[str],
    message: str,
    subject: str,
    html_message: str | None = None,
) -> None:
    if not settings.lnbits_email_notifications_enabled:
        raise ValueError("Email notifications are disabled")
    if not is_valid_email_address(settings.lnbits_email_notifications_email):
        raise ValueError(
            f"Invalid from email address: {settings.lnbits_email_notifications_email}"
        )
    if not to_emails:
        raise ValueError("No email addresses provided")
    for email in to_emails:
        if not is_valid_email_address(email):
            raise ValueError(f"Invalid email address: {email}")

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.lnbits_email_notifications_email
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject
    msg.attach(MIMEText(message, "plain"))
    if html_message:
        msg.attach(MIMEText(html_message, "html"))

    username = (
        settings.lnbits_email_notifications_username
        or settings.lnbits_email_notifications_email
    )
    with smtplib.SMTP(
        settings.lnbits_email_notifications_server,
        settings.lnbits_email_notifications_port,
    ) as smtp_server:
        smtp_server.starttls()
        smtp_server.login(username, settings.lnbits_email_notifications_password)
        smtp_server.sendmail(
            settings.lnbits_email_notifications_email,
            to_emails,
            msg.as_string(),
        )


def _ticket_url(ticket: Ticket) -> str:
    base_url = (ticket.extra.ticket_base_url or settings.lnbits_baseurl).rstrip("/")
    return f"{base_url}/events/ticket/{ticket.id}"


def _ticket_image_url(ticket: Ticket, event: Event) -> str | None:
    base_url = (ticket.extra.ticket_base_url or settings.lnbits_baseurl).rstrip("/")
    return f"{base_url}/events/api/v1/qr/{ticket.id}"


async def preview_ticket_email_html(
    event: Event, basket: Basket | None, tickets: list[Ticket], base_url: str
) -> tuple[str, str]:
    tt_map = await _build_tt_map(tickets)
    subject, text_message, html_message = _build_ticket_email(
        event, tickets, tt_map, basket, base_url
    )
    return subject, html_message


async def preview_admin_email_html(
    event: Event, basket: Basket, tickets: list[Ticket], base_url: str
) -> tuple[str, str]:
    tt_map = await _build_tt_map(tickets)
    count = len(tickets)
    grouped = _grouped_ticket_types(tickets, tt_map)
    ticket_details = "\n".join(
        f"- {name} ×{qty}"
        + (f" — {_format_price(event, price * qty)}" if price > 0 else "")
        for name, qty, price in grouped
    )
    total = sum(price * qty for _, qty, price in grouped)
    total_str = _format_price(event, total) if total > 0 else ""
    basket_url = f"{base_url}/events/basket/{basket.id}"
    text_message = (
        f"New ticket sale for '{event.name}'\n"
        f"{_format_event_dates(event)}\n\n"
        f"Order ID: {basket.id}\n"
        f"View basket: {basket_url}\n"
        f"Buyer: {_display_name(basket.name)} ({basket.email or '—'})\n"
        f"Tickets: {count}\n"
        f"Total: {total_str}\n\n"
        f"{ticket_details}"
    )
    subject = f"New sale: {count} ticket(s) for '{event.name}'"
    html_message = _render_admin_email_html(event, basket, tickets, tt_map, base_url)
    return subject, html_message


async def refund_tickets(event_id: str):
    await purge_unpaid_tickets(event_id)
    tickets = await get_event_tickets(event_id)

    if not tickets:
        return

    for ticket in tickets:
        if ticket.extra.refunded:
            continue
        if ticket.paid and ticket.extra.refund_address and ticket.extra.sats_paid:
            try:
                res = await execute(
                    ticket.extra.refund_address, str(ticket.extra.sats_paid)
                )
                if res:
                    ticket.extra.refunded = True
                    await update_ticket(ticket)
            except Exception as e:
                logger.error(f"Error refunding ticket {ticket.id}: {e}")
