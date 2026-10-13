"""Promo voucher (ticket-as-voucher) behaviour, ported from the standalone
``test.py`` suite: 16 assertions across the A-F groups.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from events import crud
from events import models as M
from events import services as S


async def make_event(redemptions=1, extra_static=None, max_tickets=None):
    ev = M.Event(
        id="EV1", wallet="w1", name="Test", info="", canceled=False,
        event_start_date="2026-01-01", event_end_date="2026-12-31",
        currency="sat", admin_email=None, allow_fiat=False, fiat_currency="GBP",
        amount_tickets=100, price_per_ticket=100, time=datetime.now(timezone.utc),
        sold=0, banner=None,
        extra=M.EventExtra(promo_codes=[
            M.PromoCode(code="TICKETID", type="ticket", discount_percent=50,
                        combinable=False, redemptions_per_ticket=redemptions,
                        max_tickets=max_tickets)
        ] + (extra_static or [])))
    await crud.create_event(ev)
    today = datetime.now(timezone.utc).date().isoformat()
    tt = M.TicketType(id="TT1", event_id="EV1", name="GA", price=100,
                      available_from=today, available_to="2026-12-31")
    await crud.create_ticket_type(tt)
    return ev


async def make_source(source_id, paid=True, extra=None, event="EV1"):
    t = M.Ticket(
        id=source_id, wallet="w1", event=event, name="Holder", email="a@b.c",
        registered=False, paid=paid, time=datetime.now(timezone.utc),
        reg_timestamp=datetime.now(timezone.utc), ticket_type_id="TT1",
        basket_id=None, extra=extra or M.TicketExtra())
    await crud.update_ticket(t)
    return t


async def calc(ev, codes, qty=1):
    return await S.calculate_basket_total(
        ev, [{"ticket_type_id": "TT1", "quantity": qty}], codes
    )


def test_a_voucher_lifecycle():
    async def run():
        ev = await make_event(redemptions=1)
        await make_source("SRC1")
        t1 = await calc(ev, ["SRC1"])
        assert t1.total == 50, "A1 voucher applies on single ticket"
        assert t1.discounts_applied[0].code == "SRC1", (
            "A2 discount attributable to source id"
        )
        await S._reserve_ticket_voucher(ev, "SRC1", "basket-A")
        src = await crud.get_ticket("SRC1")
        assert len(src.extra.ticket_id_voucher_redemptions) == 1, (
            "A3 reservation recorded pending"
        )
        assert src.extra.ticket_id_voucher_redemptions[0]["status"] == "pending", (
            "A4 reservation pending status"
        )
        with pytest.raises(ValueError):
            await S._reserve_ticket_voucher(ev, "SRC1", "basket-B")  # A5 concurrent second reservation blocked
        await S._finalize_ticket_voucher(src, "basket-A")
        src = await crud.get_ticket("SRC1")
        assert src.extra.ticket_id_voucher_redemptions[0]["status"] == "completed", (
            "A6 finalized completed"
        )
        t1b = await calc(ev, ["SRC1"])
        assert t1b.discount == 0, "A7 no discount after redemption used"

    asyncio.run(run())


def test_b_redemption_limit():
    async def run():
        ev3 = await make_event(redemptions=3)
        await make_source("SRC3")
        for i in range(3):
            await S._reserve_ticket_voucher(ev3, "SRC3", f"b3-{i}")
        t3 = await calc(ev3, ["SRC3"])
        assert t3.discount == 0, "B1 voucher blocked at limit=3"
        with pytest.raises(ValueError):
            await S._reserve_ticket_voucher(ev3, "SRC3", "b3-x")  # B2 4th reservation blocked

    asyncio.run(run())


def test_c_max_tickets_gate():
    # The voucher applicability gate is max_tickets (None = any basket size),
    # which replaced the old hardwired single-ticket basket rule.
    async def run():
        evc = await make_event(redemptions=1)
        await make_source("SRCC")
        tc = await calc(evc, ["SRCC"], qty=2)
        assert tc.discount == 100 and tc.total == 100, (
            "C1 voucher applies on multi-ticket basket when max_tickets is None"
        )
        evc2 = await make_event(redemptions=1, max_tickets=1)
        await make_source("SRCC2")
        tc2 = await calc(evc2, ["SRCC2"], qty=2)
        assert tc2.discount == 0 and tc2.total == 200, (
            "C2 voucher blocked when item_count exceeds max_tickets"
        )

    asyncio.run(run())


def test_d_unpaid_ticket_is_not_a_voucher():
    async def run():
        evd = await make_event(redemptions=1)
        await make_source("SRCD", paid=False)
        td = await calc(evd, ["SRCD"])
        assert td.discount == 0, "D1 unpaid ticket not a valid voucher"

    asyncio.run(run())


def test_e_expired_pending_pruned():
    async def run():
        eve = await make_event(redemptions=1)
        old = M.TicketExtra(ticket_id_voucher_redemptions=[{
            "basket_id": "dead", "status": "pending",
            "time": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}])
        await make_source("SRCE", extra=old)
        te = await calc(eve, ["SRCE"])
        assert te.discount == 50, "E1 expired pending not counted -> voucher available"
        await S._reserve_ticket_voucher(eve, "SRCE", "new-basket")
        src = await crud.get_ticket("SRCE")
        assert (
            len(src.extra.ticket_id_voucher_redemptions) == 1
            and src.extra.ticket_id_voucher_redemptions[0]["basket_id"] == "new-basket"
        ), "E2 expired entry pruned on reserve"

    asyncio.run(run())


def test_f_static_promo_does_not_stack():
    async def run():
        evf = await make_event(redemptions=1, extra_static=[
            M.PromoCode(code="CHEAP", discount_percent=10, combinable=True)])
        await make_source("SRCF")
        tf = await calc(evf, ["CHEAP"])
        assert tf.discount == 10, "F1 static promo still applies"
        tf2 = await calc(evf, ["CHEAP", "SRCF"])
        assert tf2.discount == 50, "F2 static+voucher does not stack"

    asyncio.run(run())
