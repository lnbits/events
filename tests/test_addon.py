"""Add-on ticket entitlements: gated offer codes that GRANT rather than
discount (the Bitflix screening-seat case).

A grant rule authorises ADDING tickets of another type, only while a
qualifying source ticket is present (in the basket, or presented by id), never
beyond ``per_source x admits`` per source ticket, and never past the add-on
type's counted cap.
"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from events import crud
from events import models as M
from events import services as S

TODAY = datetime.now(timezone.utc).date().isoformat()

WEEKEND = "WEEKEND"
FAMILY = "FAMILY"
ADDON = "ADDON"


async def make_event(addon_cap=100):
    rule = M.PromoCode(
        code="",
        source=M.PromoSource(require_ticket=True, ticket_type_ids=[WEEKEND, FAMILY]),
        grants=M.PromoGrant(ticket_type_id=ADDON, per_source=1),
    )
    ev = M.Event(
        id="EV1", wallet="w1", name="Bitfest", info="", canceled=False,
        event_start_date="2026-01-01", event_end_date="2026-12-31",
        currency="GBP", admin_email=None, allow_fiat=False, fiat_currency="GBP",
        amount_tickets=100, price_per_ticket=149, time=datetime.now(timezone.utc),
        sold=0, banner=None, extra=M.EventExtra(promo_codes=[rule]),
    )
    await crud.create_event(ev)
    for tid, name, price, admits, cap in [
        (WEEKEND, "Single - Weekend", 149, 1, 500),
        (FAMILY, "Family - Weekend", 399, 4, 50),
        (ADDON, "Bitflix - The Six Billion Dollar Man", 0, 1, addon_cap),
    ]:
        await crud.create_ticket_type(M.TicketType(
            id=tid, event_id="EV1", name=name, price=price, max_tickets=cap,
            available_from=TODAY, available_to="2026-12-31",
            sort_order=0, extra={"admits": admits},
        ))
    return ev


async def make_ticket(ticket_id, ticket_type_id, paid=True, event="EV1", extra=None):
    t = M.Ticket(
        id=ticket_id, wallet="w1", event=event, name="Holder", email="a@b.c",
        registered=False, paid=paid, time=datetime.now(timezone.utc),
        reg_timestamp=datetime.now(timezone.utc), ticket_type_id=ticket_type_id,
        basket_id=None, extra=extra or M.TicketExtra(),
    )
    await crud.update_ticket(t)
    return t


def items(*pairs):
    return [SimpleNamespace(ticket_type_id=tid, quantity=q) for tid, q in pairs]


async def gate(ev, basket_items, presented=()):
    """Run the real resolution + the add-on gate, as the checkout does."""
    ticket_types = await S.get_ticket_types(ev.id)
    reservation = await S._resolve_ticket_rules(
        ev, list(presented), sum(i.quantity for i in basket_items)
    )
    await S._validate_addon_items(ev, basket_items, ticket_types, reservation)


# --- model invariants -------------------------------------------------------

def test_grant_implies_the_source_gate():
    """A stored grant with no explicit source condition still loads, and is
    read as requiring a ticket — otherwise the codeless rule is invalid and
    the whole event fails to load."""
    promo = M.PromoCode(code="", grants=M.PromoGrant(ticket_type_id=ADDON))
    assert promo.grants is not None
    assert promo.source.require_ticket is True


def test_grant_clears_any_discount():
    promo = M.PromoCode(
        code="", discount_percent=50,
        source=M.PromoSource(require_ticket=True),
        grants=M.PromoGrant(ticket_type_id=ADDON, per_source=2),
    )
    assert promo.grants.per_source == 2
    assert promo.discount_percent is None, "cannot both discount and grant"


def test_per_source_must_be_positive():
    with pytest.raises(Exception):
        M.PromoGrant(ticket_type_id=ADDON, per_source=0)


def test_admits_defaults_and_survives_junk():
    assert S.ticket_admits(None) == 1
    assert S.ticket_admits(M.TicketType(
        id="x", event_id="EV1", name="n", available_from=TODAY,
        available_to="2026-12-31", extra={})) == 1
    assert S.ticket_admits(M.TicketType(
        id="x", event_id="EV1", name="n", available_from=TODAY,
        available_to="2026-12-31", extra={"admits": "4"})) == 4
    assert S.ticket_admits(M.TicketType(
        id="x", event_id="EV1", name="n", available_from=TODAY,
        available_to="2026-12-31", extra={"admits": "junk"})) == 1


# --- the count itself ---------------------------------------------------------

def test_sold_counts_is_committed_seats_only():
    def mk(i, ttype, paid=True, refunded=False, deactivated=False):
        return M.Ticket(
            id=i, wallet="w", event="EV1", name="n", email="a@b.c", registered=False,
            paid=paid, time=datetime.now(timezone.utc), ticket_type_id=ttype,
            extra=M.TicketExtra(refunded=refunded, deactivated=deactivated))
    tickets = [
        mk("1", "A"), mk("2", "A"),
        mk("3", "A", paid=False),          # unpaid basket
        mk("4", "A", refunded=True),       # refunded frees the seat
        mk("5", "A", deactivated=True),    # an upgrade voids its source
        mk("6", "B"),
        mk("7", None),                     # no type -> not attributable
    ]
    assert M.sold_counts(tickets) == {"A": 2, "B": 1}


def test_sold_is_derived_not_the_stored_column():
    """The stored `sold` drifts (imported tickets skip the increment). Readers
    must derive it from the rows, so a wrong column cannot leak a cap."""
    async def run():
        await make_event()
        tt = await crud.get_ticket_type(ADDON)
        tt.sold = 999
        await crud.update_ticket_type(tt)
        await make_ticket("S1", ADDON)
        await make_ticket("S2", ADDON, paid=False)
        types = {t.id: t for t in await crud.get_ticket_types("EV1")}
        assert types[ADDON].sold == 1, "derived from rows, ignoring the stored 999"
    asyncio.run(run())


def test_addon_cap_counts_only_committed_seats():
    async def run():
        ev = await make_event(addon_cap=2)
        await make_ticket("U1", ADDON, paid=False)                       # abandoned
        await make_ticket("R1", ADDON, extra=M.TicketExtra(refunded=True))
        await gate(ev, items((WEEKEND, 2), (ADDON, 2)))                  # 2 committed -> fits
        await make_ticket("P1", ADDON)                                   # now 1 committed
        with pytest.raises(ValueError):
            await gate(ev, items((WEEKEND, 2), (ADDON, 2)))              # 1+2 > 2
        await gate(ev, items((WEEKEND, 2), (ADDON, 1)))                  # only 1 left
    asyncio.run(run())


# --- the gate ---------------------------------------------------------------

def test_addon_alone_is_refused():
    async def run():
        ev = await make_event()
        with pytest.raises(ValueError) as exc:
            await gate(ev, items((ADDON, 1)))
        assert "qualifying ticket" in str(exc.value)
    asyncio.run(run())


def test_weekend_in_the_basket_authorises_one():
    async def run():
        ev = await make_event()
        await gate(ev, items((WEEKEND, 1), (ADDON, 1)))          # allowed
        with pytest.raises(ValueError):
            await gate(ev, items((WEEKEND, 1), (ADDON, 2)))      # one per person
        await gate(ev, items((WEEKEND, 2), (ADDON, 2)))          # two tickets, two seats
    asyncio.run(run())


def test_family_weekend_authorises_four():
    async def run():
        ev = await make_event()
        await gate(ev, items((FAMILY, 1), (ADDON, 4)))           # allowed
        with pytest.raises(ValueError):
            await gate(ev, items((FAMILY, 1), (ADDON, 5)))       # one too many
    asyncio.run(run())


def test_presented_ticket_authorises_one():
    async def run():
        ev = await make_event()
        await make_ticket("SRC1", WEEKEND)
        await gate(ev, items((ADDON, 1)), presented=["SRC1"])    # allowed
        with pytest.raises(ValueError):
            await gate(ev, items((ADDON, 2)), presented=["SRC1"])
    asyncio.run(run())


def test_presented_family_ticket_authorises_four():
    async def run():
        ev = await make_event()
        await make_ticket("SRC2", FAMILY)
        await gate(ev, items((ADDON, 4)), presented=["SRC2"])    # allowed
        with pytest.raises(ValueError):
            await gate(ev, items((ADDON, 5)), presented=["SRC2"])
    asyncio.run(run())


def test_cross_event_source_keeps_its_admits():
    """A source ticket belonging to ANOTHER event must still be worth its
    admits rather than defaulting to one: the allowance looks its type up."""
    async def run():
        ev = await make_event()
        other = M.Event(
            id="EV2", wallet="w1", name="Freedom Fest", info="", canceled=False,
            event_start_date="2026-01-01", event_end_date="2026-12-31",
            currency="GBP", admin_email=None, allow_fiat=False, fiat_currency="GBP",
            amount_tickets=10, price_per_ticket=119, time=datetime.now(timezone.utc),
            sold=0, banner=None, extra=M.EventExtra(promo_codes=[]),
        )
        await crud.create_event(other)
        await crud.create_ticket_type(M.TicketType(
            id="FF_FAMILY", event_id="EV2", name="Family (Full Access)", price=119,
            max_tickets=21, available_from=TODAY, available_to="2026-12-31",
            sort_order=0, extra={"admits": 4},
        ))
        rule = ev.extra.promo_codes[0]
        rule.source.event_ids = ["EV1", "EV2"]
        rule.source.ticket_type_ids = [WEEKEND, FAMILY, "FF_FAMILY"]
        await crud.update_event(ev)
        await crud.update_ticket(M.Ticket(
            id="FF1", wallet="w1", event="EV2", name="Holder", email="a@b.c",
            registered=False, paid=True, time=datetime.now(timezone.utc),
            reg_timestamp=datetime.now(timezone.utc), ticket_type_id="FF_FAMILY",
            basket_id=None, extra=M.TicketExtra()))
        await gate(ev, items((ADDON, 4)), presented=["FF1"])      # four allowed
        with pytest.raises(ValueError):
            await gate(ev, items((ADDON, 5)), presented=["FF1"])  # not five
    asyncio.run(run())


def test_unpaid_source_is_refused():
    async def run():
        ev = await make_event()
        await make_ticket("SRC3", WEEKEND, paid=False)
        with pytest.raises(ValueError) as exc:
            await gate(ev, items((ADDON, 1)), presented=["SRC3"])
        assert "qualifying ticket" in str(exc.value)
    asyncio.run(run())


def test_addon_is_never_its_own_source():
    async def run():
        ev = await make_event()
        await make_ticket("A1", ADDON)
        with pytest.raises(ValueError):
            await gate(ev, items((ADDON, 2)), presented=["A1"])
    asyncio.run(run())


def test_counted_cap_is_enforced():
    async def run():
        ev = await make_event(addon_cap=2)
        await make_ticket("B1", ADDON)                            # 1 already issued
        await gate(ev, items((WEEKEND, 2), (ADDON, 1)))           # allowance 2, 1 left
        with pytest.raises(ValueError) as exc:
            await gate(ev, items((WEEKEND, 2), (ADDON, 2)))       # 1 left of a cap of 2
        assert "left" in str(exc.value)
    asyncio.run(run())


def test_shared_cap_spans_events():
    """Types sharing extra.cap_group consume ONE pool, so issuing seats on
    another event's checkout eats this one's headroom."""
    async def run():
        ev = await make_event(addon_cap=3)
        await crud.create_ticket_type(M.TicketType(
            id="ADDON_FF", event_id="EV2", name="Bitflix (Freedom Fest)", price=0,
            max_tickets=3, available_from=TODAY, available_to="2026-12-31",
            sort_order=0, extra={"admits": 1, "cap_group": "bitflix"}))
        tt = await crud.get_ticket_type(ADDON)
        tt.extra = {**tt.extra, "cap_group": "bitflix"}
        await crud.update_ticket_type(tt)
        await make_ticket("F1", "ADDON_FF", event="EV2")
        await make_ticket("F2", "ADDON_FF", event="EV2")
        # two weekend tickets authorise two seats, so the CAP is what refuses
        await gate(ev, items((WEEKEND, 2), (ADDON, 1)))            # 1 seat left of 3
        with pytest.raises(ValueError) as exc:
            await gate(ev, items((WEEKEND, 2), (ADDON, 2)))        # only 1 left
        assert "left" in str(exc.value)
    asyncio.run(run())


def test_grant_rule_discounts_nothing():
    """A grant rule must not leak into the discount engine."""
    async def run():
        ev = await make_event()
        totals = await S.calculate_basket_total(
            ev, [{"ticket_type_id": WEEKEND, "quantity": 1}], []
        )
        assert totals.total == 149 and totals.discount == 0, (
            "no discount applied for a grant rule with no source presented"
        )
    asyncio.run(run())


# --- end to end: the zero-total claim ---------------------------------------

def test_zero_total_addon_basket_issues_and_activates():
    async def run():
        ev = await make_event()
        await make_ticket("SRC9", WEEKEND)
        S._send_basket_notifications_in_background = lambda *a, **k: None
        data = M.CreateBasket(
            name="Holder", email="a@b.c",
            items=[M.BasketItem(ticket_type_id=ADDON, quantity=1)],
            promo_codes=["SRC9"],
        )
        basket, tickets, totals, charge = await S.create_basket_with_charge(
            ev, data, "key", "https://example.test"
        )
        assert totals.total == 0, "the add-on is free"
        assert charge is None, "no payment is requested for a zero-total basket"
        assert basket.paid is True, "zero-total basket activates immediately"
        assert len(tickets) == 1 and tickets[0].ticket_type_id == ADDON
        src = await crud.get_ticket("SRC9")
        assert src.extra.ticket_id_voucher_redemptions[0]["status"] == "completed", (
            "the claim is finalized against the source ticket"
        )
    asyncio.run(run())
