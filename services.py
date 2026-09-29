from __future__ import annotations

import asyncio
import smtplib
from asyncio.tasks import create_task
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Any, NamedTuple

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
    get_events,
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
    PromoRejection,
    PromoRequirement,
    PromoSource,
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
    """Total discount a promo yields against ``price``.

    A ticket-source promo resolved with ``credit="paid"`` also contributes the
    source ticket's recorded paid value. The credit is applied first and the
    promo's own percent/fixed value sits on top of the target price; the whole
    thing is capped at the base, so an upgrade can become free (cap to free)
    but never negative.
    """
    discount = 0.0
    credit = getattr(promo, "credit_value", None)
    if credit:
        discount += float(credit)
    if promo.discount_percent is not None:
        discount += price * promo.discount_percent / 100
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
_VOUCHER_TTL_SECONDS = 24 * 3600  # matches the satspay charge time (1440 min)

# Per-SOURCE-TICKET locks so concurrent checkouts cannot both claim the last
# redemption slot of one source ticket. Keyed on the source ticket id rather
# than the target event, because a ticket-source promo may reference a ticket
# that belongs to a different event.
_reservation_locks: dict[str, asyncio.Lock] = {}


def _reservation_lock(key: str) -> asyncio.Lock:
    if key not in _reservation_locks:
        _reservation_locks[key] = asyncio.Lock()
    return _reservation_locks[key]


def _promo_source(promo) -> PromoSource:
    """The promo's ticket condition, tolerating legacy/constructed objects."""
    source = getattr(promo, "source", None)
    if isinstance(source, PromoSource):
        return source
    # construct()'d or pre-axis object: fall back to the legacy discriminators.
    legacy_type = getattr(promo, "type", None)
    return PromoSource(require_ticket=legacy_type == "ticket")


def _requires_ticket(promo) -> bool:
    return bool(_promo_source(promo).require_ticket)


def _rule_code(promo) -> str:
    """The offer code a promo is selected by ("" = activated by a ticket alone)."""
    return (getattr(promo, "code", "") or "").upper()


def _ticket_rules(event: Event, active_only: bool = True) -> list[PromoCode]:
    """Every promo that ALSO requires a source ticket.

    Plural by design: an event may carry any number of these, distinguished by
    their offer codes (an upgrade rule, a bring-a-friend rule, ...). This used
    to return a single rule, which made offers indistinguishable.
    ``active_only=False`` is used when consuming an already-paid basket, so a
    promo deactivated mid-checkout still voids its source ticket.
    """
    return [
        p for p in event.extra.promo_codes
        if _requires_ticket(p) and (p.active or not active_only)
    ]


def _source_scope_matches(promo, source: Ticket, event: Event) -> bool:
    source_axis = _promo_source(promo)
    if not source_axis.require_ticket:
        return False
    # No source events named = this event only (the pre-existing behaviour).
    allowed_events = source_axis.event_ids or [event.id]
    if source.event not in allowed_events:
        return False
    if (source_axis.ticket_type_ids
            and source.ticket_type_id not in source_axis.ticket_type_ids):
        return False
    return True


async def _resolve_source_ticket(
    event: Event, ticket_id: str, promo: PromoCode
) -> tuple[Ticket | None, str | None]:
    """Resolve a submitted ticket id against a ticket rule.

    Returns ``(ticket, None)`` on success or ``(None, reason)`` — the reason is
    a stable code the checkout can show, instead of failing silently.
    """
    if not ticket_id:
        return None, "ticket_not_found"
    source = await get_ticket(ticket_id)
    if not source:
        return None, "ticket_not_found"
    if not source.paid or source.extra.deactivated or source.extra.refunded:
        return None, "ticket_not_eligible"
    if source.extra.upgraded_to:
        return None, "ticket_already_used"
    if not _source_scope_matches(promo, source, event):
        return None, "ticket_out_of_scope"
    source_event = await get_event(source.event)
    if not source_event:
        return None, "ticket_not_found"
    if (source_event.currency or "").lower() != (event.currency or "").lower():
        return None, "currency_mismatch"
    return source, None


async def _source_credit(promo, source: Ticket) -> float:
    """Credit contributed by the source ticket, in the target event's currency."""
    if _promo_source(promo).credit != "paid":
        return 0.0
    value = source.extra.paid_value
    if value is None and source.ticket_type_id:
        # Tickets sold before paid_value was recorded fall back to the ticket
        # type's price (the documented backfill fallback).
        ticket_type = await get_ticket_type(source.ticket_type_id)
        if ticket_type:
            value = ticket_type.price
    return float(value or 0)


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


def _source_gate_ok(promo, item_count: int) -> bool:
    """Whether the promo may apply to a basket of ``item_count`` tickets."""
    source_axis = _promo_source(promo)
    # A move upgrade is strictly one ticket in, one ticket out.
    if source_axis.move and item_count != 1:
        return False
    if promo.max_tickets is not None and item_count > promo.max_tickets:
        return False
    return True


async def _match_ticket_rule(
    event: Event, ticket_id: str, item_count: int, active_only: bool = True
) -> tuple[PromoCode, Ticket] | None:
    """Find the ticket rule a submitted ticket id satisfies (rule order wins)."""
    for promo in _ticket_rules(event, active_only=active_only):
        if not _source_gate_ok(promo, item_count):
            continue
        source, _reason = await _resolve_source_ticket(event, ticket_id, promo)
        if source:
            return promo, source
    return None


async def _reserve_ticket_voucher(
    event: Event, source_ticket_id: str, basket_id: str, item_count: int = 1
) -> None:
    """Authoritative, concurrency-safe reservation of one redemption slot.

    Callers must hold the lock for ``source_ticket_id``.
    """
    match = await _match_ticket_rule(event, source_ticket_id, item_count)
    if not match:
        raise ValueError("Invalid or ineligible ticket ID for discount.")
    promo, source = match
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


async def _consume_upgraded_source(
    promo, source: Ticket, successor_ticket_id: str | None
) -> None:
    """Void a source ticket consumed by a move upgrade and release its seat.

    The seat is only released when the source ticket had not been used: an
    already-registered/attended ticket still represents a seat that was
    occupied, so decrementing ``sold`` would over-state availability.
    """
    source.extra.deactivated = True
    source.extra.upgraded_to = successor_ticket_id
    await update_ticket(source)

    if not source.registered:
        source_event = await get_event(source.event)
        if source_event and source_event.sold > 0:
            source_event.sold -= 1
            await update_event(source_event)
        if source.ticket_type_id:
            ticket_type = await get_ticket_type(source.ticket_type_id)
            if ticket_type and ticket_type.sold > 0:
                ticket_type.sold -= 1
                await update_ticket_type(ticket_type)

    if successor_ticket_id:
        successor = await get_ticket(successor_ticket_id)
        if successor:
            successor.extra.upgraded_from = source.id
            await update_ticket(successor)


async def backfill_paid_values(wallet_ids: str | list[str]) -> dict:
    """Backfill ``TicketExtra.paid_value`` for tickets sold before it existed.

    Prefers reconstructing the charged amount from the ticket's basket, falling
    back to the ticket type's price when a basket can't be resolved. Idempotent:
    only fills tickets whose ``paid_value`` is still None.
    """
    summary = {
        "events": 0,
        "filled": 0,
        "basket_reconstructed": 0,
        "type_price_fallback": 0,
    }
    for event in await get_events(wallet_ids):
        summary["events"] += 1
        basket_cache: dict[str, list[Ticket]] = {}
        for ticket in await get_event_tickets(event.id):
            if not ticket.paid or ticket.extra.paid_value is not None:
                continue
            value = None
            if ticket.basket_id:
                basket = await get_basket(ticket.basket_id)
                if basket:
                    siblings = basket_cache.get(ticket.basket_id)
                    if siblings is None:
                        siblings = await get_basket_tickets(ticket.basket_id)
                        basket_cache[ticket.basket_id] = siblings
                    total = basket.total
                    if total is None:
                        total = await _recompute_basket_total(basket, event)
                    if total:
                        value = float(total) / len(siblings or [ticket])
                        summary["basket_reconstructed"] += 1
            if value is None and ticket.ticket_type_id:
                ticket_type = await get_ticket_type(ticket.ticket_type_id)
                if ticket_type:
                    value = float(ticket_type.price)
                    summary["type_price_fallback"] += 1
            if value is None:
                continue
            ticket.extra.paid_value = value
            await update_ticket(ticket)
            summary["filled"] += 1
    return summary


class _TicketRuleResolution(NamedTuple):
    """Outcome of pairing submitted offer codes + ticket ids against the rules."""

    promos: list[PromoCode]
    # (rule, ticket-id token, source ticket) for every rule that actually applied
    pairs: list[tuple[PromoCode, str, Ticket]]
    pending: list[PromoRequirement]
    rejections: list[PromoRejection]


def _rule_selected(rule, selected: set[str]) -> bool:
    """Whether the buyer chose this rule (a codeless rule is always chosen)."""
    rule_code = _rule_code(rule)
    return (not rule_code) or (rule_code in selected)


def _rule_uses_available(rule, allow_consumed: bool) -> bool:
    """Whether a rule still has global uses left.

    A ticket rule can now cap its own usage ("first 20 upgrades"), which the
    retired code-less design could not express because every rule shared an
    empty code and so could not be counted.
    """
    if allow_consumed:
        return True
    max_uses = getattr(rule, "max_uses", None)
    if max_uses is None:
        return True
    return (getattr(rule, "used_count", 0) or 0) < max_uses


async def _resolve_ticket_rules(
    event: Event,
    promo_codes: list[str],
    item_count: int,
    *,
    allow_consumed: bool = False,
) -> _TicketRuleResolution:
    """Pair submitted offer codes and ticket ids against the ticket rules.

    A token matching a rule's offer code is an OFFER CODE; every other token is
    a TICKET-ID CANDIDATE (ticket ids are case-sensitive PKs, so candidates keep
    their raw case while codes compare uppercased). A rule applies when it was
    SELECTED (its code typed, or it has no code) and a candidate resolves
    against it.

    Two outcomes are reported rather than swallowed, because a silent
    no-discount is indistinguishable from a wrong code:

    * ``pending``    — a rule was selected but no ticket was supplied at all.
      This is what drives the checkout's "now enter your ticket ID" prompt.
    * ``rejections`` — a ticket was supplied and did not work, with a stable
      reason code.

    Rule order decides ties: the first eligible rule a ticket satisfies wins.
    """
    rules = _ticket_rules(event)
    if not rules:
        return _TicketRuleResolution([], [], [], [])

    offer_codes = {
        _rule_code(p) for p in event.extra.promo_codes if _rule_code(p)
    }
    selected = {c.upper() for c in promo_codes if c.upper() in offer_codes}
    candidates = [c for c in promo_codes if c.upper() not in offer_codes]

    # Probe each candidate against each eligible rule, once. A ticket may
    # satisfy more than one rule, so rank the offers the buyer actually named
    # FIRST — otherwise a ticket would bind to whichever rule happens to sit
    # earliest in the event config and the typed offer code would be ignored.
    # A codeless rule (applies to any eligible ticket) outranks an un-named
    # coded offer, but not a named one.
    def _rank(rule) -> int:
        rule_code = _rule_code(rule)
        if rule_code and rule_code in selected:
            return 0
        return 1 if not rule_code else 2

    resolved: dict[tuple[int, str], Ticket] = {}
    reasons: dict[str, str] = {}
    exhausted: set[str] = set()
    gate_blocked: set[str] = set()
    for token in candidates:
        for idx in sorted(range(len(rules)), key=lambda i: (_rank(rules[i]), i)):
            rule = rules[idx]
            # Resolve BEFORE the basket-shape gate so a valid ticket that simply
            # doesn't fit the basket gets an accurate reason instead of falling
            # through to a generic one.
            source, reason = await _resolve_source_ticket(event, token, rule)
            if not source:
                reasons.setdefault(token, reason or "ticket_not_found")
                continue
            if not _source_gate_ok(rule, item_count):
                # The ticket is fine; the BASKET shape is what this rule refuses.
                gate_blocked.add(token)
                continue
            if not _rule_uses_available(rule, allow_consumed):
                # The ticket is fine; the OFFER has run out. Remember it so the
                # reason below is accurate rather than a generic one.
                exhausted.add(token)
                continue
            resolved[(idx, token)] = source
            break

    now = datetime.now(timezone.utc)
    promos: list[PromoCode] = []
    pairs: list[tuple[PromoCode, str, Ticket]] = []
    pending: list[PromoRequirement] = []
    rejections: list[PromoRejection] = []
    rejected: set[str] = set()

    for idx, rule in enumerate(rules):
        if not _rule_selected(rule, selected):
            continue
        if not _source_gate_ok(rule, item_count):
            continue
        token = next((t for t in candidates if (idx, t) in resolved), None)
        if token is None:
            # No usable ticket. Prompt only when the buyer supplied nothing at
            # all; otherwise the per-token rejection below explains the failure.
            if not candidates and _rule_code(rule):
                pending.append(
                    PromoRequirement(code=rule.code, requires="ticket_id")
                )
            continue
        source = resolved[(idx, token)]
        if not allow_consumed and not _ticket_voucher_available(source, rule, now):
            rejections.append(
                PromoRejection(code=token, reason="ticket_redemptions_exhausted")
            )
            rejected.add(token)
            continue
        credit = await _source_credit(rule, source)
        promos.append(
            # construct() bypasses validation so the rule passes through with
            # the resolved credit. `code` is the offer code so the buyer sees
            # WHICH offer applied and max_uses can count it; a codeless rule
            # falls back to the ticket id so the checkout still shows something
            # identifying rather than a blank.
            PromoCode.construct(
                code=rule.code or token,
                source=_promo_source(rule),
                discount_percent=rule.discount_percent,
                discount_fixed=rule.discount_fixed,
                active=True,
                combinable=rule.combinable,
                max_uses=None,
                used_count=0,
                ticket_type_ids=rule.ticket_type_ids,
                max_tickets=rule.max_tickets,
                credit_value=credit,
            )
        )
        pairs.append((rule, token, source))

    # Every candidate that did not produce a discount gets a reason — a ticket
    # supplied without its offer code must not fail silently either, and a token
    # must never collect two explanations.
    used = {token for _rule, token, _source in pairs}
    for token in candidates:
        if token in used or token in rejected:
            continue
        reason = reasons.get(token)
        if reason is None:
            if token in exhausted:
                reason = "promo_uses_exhausted"
            elif token in gate_blocked:
                reason = "ticket_count_not_eligible"
            else:
                matches_unselected = any(
                    (idx, token) in resolved
                    and not _rule_selected(rules[idx], selected)
                    for idx in range(len(rules))
                )
                reason = (
                    "ticket_needs_offer_code"
                    if matches_unselected
                    else "ticket_not_applicable"
                )
        rejections.append(PromoRejection(code=token, reason=reason))

    return _TicketRuleResolution(promos, pairs, pending, rejections)


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
    # Plain promos: identified by their offer code, no ticket involved. Ticket
    # rules selected by the same code are resolved separately below.
    promos = [
        p for p in event.extra.promo_codes
        if not _requires_ticket(p) and p.code and p.code in submitted
    ]

    item_count = sum(item.get("quantity", 1) for item in items)
    resolution = await _resolve_ticket_rules(
        event, promo_codes, item_count, allow_consumed=allow_consumed
    )
    promos.extend(resolution.promos)

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
        pending=resolution.pending,
        rejections=resolution.rejections,
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
    # Keep the RAW submitted codes so ticket-source promos (whose codes are
    # case-sensitive ticket ids) survive into basket.promo_codes. Literal-code
    # matching upper-cases at the point of comparison.
    promo_code_strings = list(data.promo_codes)

    item_count = sum(i.quantity for i in data.items)

    # Authoritatively reserve ticket-rule redemptions on their SOURCE tickets.
    # This is the write that closes the single-use race: it happens under a lock
    # keyed on the SOURCE ticket id, before any charge is created, so two
    # concurrent checkouts — in this event or any other — can't both claim the
    # last available slot of the same source ticket. Only rules that actually
    # applied get a reservation, so a stray token can never block checkout.
    reservation = await _resolve_ticket_rules(event, promo_code_strings, item_count)
    for _rule, token, _source in reservation.pairs:
        async with _reservation_lock(token):
            await _reserve_ticket_voucher(
                event, token, basket_id, item_count=item_count
            )

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
        total=float(totals.total),
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


async def _recompute_basket_total(basket: Basket, event: Event) -> float:
    """Total for a basket created before Basket.total existed."""
    items = []
    for ticket in await get_basket_tickets(basket.id):
        if ticket.ticket_type_id:
            items.append({"ticket_type_id": ticket.ticket_type_id, "quantity": 1})
    if not items:
        return 0.0
    totals = await calculate_basket_total(
        event, items, list(basket.promo_codes or []), allow_consumed=True
    )
    return float(totals.total)


async def _activate_basket_tickets(
    basket: Basket, tickets: list[Ticket], event: Event
) -> None:
    # Stamp each ticket with the amount actually charged, in the event's
    # currency. This is the credit basis if the ticket is later upgraded:
    # deriving credit from what was paid (rather than the ticket type's face
    # price) means a chain of upgrades can never inflate its own value.
    if tickets:
        charged = basket.total
        if charged is None:
            charged = await _recompute_basket_total(basket, event)
        share = float(charged or 0) / len(tickets)
        for ticket in tickets:
            if ticket.extra.paid_value is None:
                ticket.extra.paid_value = share

    for ticket in tickets:
        await set_ticket_paid(ticket)
    basket.paid = True
    await update_basket(basket)
    await _increment_promo_uses_from_basket(event, basket)

    # Finalize ticket-source redemptions (pending -> completed) now that this
    # basket is actually paid, and consume the source ticket for move upgrades.
    # Resolution here ignores `active` so that deactivating a promo between
    # checkout and payment can never leave a discounted ticket paid while the
    # source ticket stays valid.
    item_count = len(tickets) or 1
    offer_codes = {
        _rule_code(p) for p in event.extra.promo_codes if _rule_code(p)
    }
    for token in basket.promo_codes or []:
        if token.upper() in offer_codes:
            continue
        match = await _match_ticket_rule(
            event, token, item_count, active_only=False
        )
        if not match:
            continue
        rule, source = match
        await _finalize_ticket_voucher(source, basket.id)
        if _promo_source(rule).move:
            successor = tickets[0].id if tickets else None
            await _consume_upgraded_source(rule, source, successor)
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
