"""Upgrade / source-axis suite (Option B: PromoCode.source), ported from the
standalone ``test_upgrade.py`` suite: 37 assertions (U1-U21, V1-V9, W1-W8).

Runs against the real ``events.services`` + ``events.models`` with the stubbed
lnbits modules and in-memory CRUD provided by ``tests/conftest.py``.
"""
import asyncio
from datetime import datetime, timezone

import pytest

from events import crud
from events import models as M
from events import services as S

# Keep activation free of background email tasks.
S._send_basket_notifications_in_background = lambda *a, **k: None

TODAY = datetime.now(timezone.utc).date().isoformat()


def approx(a, b, tol=0.011):
    return abs(a - b) <= tol


def mk_event(eid, currency="GBP", promos=None):
    return M.Event(
        id=eid, wallet="w1", name=eid, info="", canceled=False,
        event_start_date="2026-01-01", event_end_date="2026-12-31", currency=currency,
        admin_email=None, allow_fiat=False, fiat_currency="GBP", amount_tickets=1000,
        price_per_ticket=100, time=datetime.now(timezone.utc), sold=0, banner=None,
        extra=M.EventExtra(promo_codes=list(promos or [])))


def mk_type(tid, eid, price):
    return M.TicketType(id=tid, event_id=eid, name=tid, price=price,
                        available_from=TODAY, available_to="2026-12-31")


def mk_ticket(tid, eid, type_id, paid=True, paid_value=None, registered=False,
              deactivated=False, refunded=False, upgraded_to=None, basket_id=None):
    return M.Ticket(
        id=tid, wallet="w1", event=eid, name="Holder", email="a@b.c",
        registered=registered, paid=paid, time=datetime.now(timezone.utc),
        reg_timestamp=datetime.now(timezone.utc), ticket_type_id=type_id,
        basket_id=basket_id,
        extra=M.TicketExtra(paid_value=paid_value, deactivated=deactivated,
                            refunded=refunded, upgraded_to=upgraded_to))


def one(tid, qty=1):
    return [{"ticket_type_id": tid, "quantity": qty}]


def two(tid, qty=2):
    """A basket bigger than the single-ticket rules, for the shape gate."""
    return [{"ticket_type_id": tid, "quantity": qty}]


def upgrade(**over):
    """A move upgrade: source credit + optional extra, scoped to TT_T1."""
    base = dict(
        source=M.PromoSource(require_ticket=True, event_ids=["EVS"], move=True, credit="paid"),
        discount_percent=None, discount_fixed=None, combinable=False,
        ticket_type_ids=["TT_T1"], redemptions_per_ticket=1,
    )
    base.update(over)
    return M.PromoCode(**base)


def friend_rule():
    return M.PromoCode(source=M.PromoSource(require_ticket=True, event_ids=["EVS"]),
                       discount_percent=50, combinable=False, max_tickets=3)


async def calc(ev, codes, items):
    return await S.calculate_basket_total(ev, items, codes)


async def _setup():
    """Seed the source/target/other/currency events and SRC1, return (src, tgt)."""
    src = mk_event("EVS", "GBP")          # source event
    tgt = mk_event("EVT", "GBP")          # target event (rules live here)
    other = mk_event("EVX", "GBP")
    sat = mk_event("EVC", "sat")          # different currency
    for ev in (src, tgt, other, sat):
        await crud.create_event(ev)
    await crud.create_ticket_type(mk_type("TT_S", "EVS", 50))
    await crud.create_ticket_type(mk_type("TT_T1", "EVT", 200))
    await crud.create_ticket_type(mk_type("TT_T2", "EVT", 60))
    await crud.create_ticket_type(mk_type("TT_C", "EVC", 80))
    await crud.update_ticket(mk_ticket("SRC1", "EVS", "TT_S", paid_value=50))
    return src, tgt


# ---------------------------------------------------------------- U1-U2
def test_upgrade_credit_only_and_extra_incentive():
    async def run():
        src, tgt = await _setup()
        tgt.extra.promo_codes = [upgrade()]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC1"], one("TT_T1"))
        assert approx(r.discount, 50) and approx(r.total, 150), (
            f"U1 upgrade pays the difference (200-50) ({r.discount}/{r.total})"
        )
        tgt.extra.promo_codes = [upgrade(discount_fixed=20)]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC1"], one("TT_T1"))
        assert approx(r.discount, 70) and approx(r.total, 130), (
            f"U2 credit + extra fixed incentive ({r.discount}/{r.total})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U3
def test_upgrade_credit_capped_at_target_price():
    async def run():
        src, tgt = await _setup()
        await crud.update_ticket(mk_ticket("SRC_BIG", "EVS", "TT_S", paid_value=500))
        tgt.extra.promo_codes = [upgrade()]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC_BIG"], one("TT_T1"))
        assert approx(r.discount, 200) and approx(r.total, 0), (
            f"U3 credit capped at target price (free, never negative) ({r.discount}/{r.total})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U4
def test_upgrade_discounts_only_its_target_type():
    async def run():
        src, tgt = await _setup()
        tgt.extra.promo_codes = [upgrade()]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC1"], one("TT_T2"))
        assert approx(r.discount, 0) and approx(r.total, 60), (
            f"U4 upgrade discounts only its target type ({r.discount}/{r.total})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U5
def test_unnamed_source_event_is_same_event_only():
    async def run():
        src, tgt = await _setup()
        tgt.extra.promo_codes = [M.PromoCode(
            source=M.PromoSource(require_ticket=True, move=True, credit="paid"),
            combinable=False, ticket_type_ids=["TT_T1"])]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC1"], one("TT_T1"))
        assert approx(r.discount, 0), (
            f"U5 unnamed source event is not cross-event eligible ({r.discount})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U6
def test_cross_currency_source_is_rejected():
    async def run():
        src, tgt = await _setup()
        await crud.update_ticket(mk_ticket("SRC_SAT", "EVC", "TT_C", paid_value=80))
        tgt.extra.promo_codes = [upgrade(source=M.PromoSource(
            require_ticket=True, event_ids=["EVC"], move=True, credit="paid"))]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC_SAT"], one("TT_T1"))
        assert approx(r.discount, 0), f"U6 cross-currency source is rejected ({r.discount})"

    asyncio.run(run())


# ---------------------------------------------------------------- U7
def test_consumed_source_cannot_be_reused():
    async def run():
        src, tgt = await _setup()
        await crud.update_ticket(mk_ticket("SRC_USED", "EVS", "TT_S", paid_value=50,
                                           upgraded_to="SOMETHING"))
        tgt.extra.promo_codes = [upgrade()]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC_USED"], one("TT_T1"))
        assert approx(r.discount, 0), f"U7 consumed source cannot be reused ({r.discount})"

    asyncio.run(run())


# ---------------------------------------------------------------- U8
def test_deactivated_or_refunded_sources_rejected():
    async def run():
        src, tgt = await _setup()
        await crud.update_ticket(mk_ticket("SRC_DEAD", "EVS", "TT_S", paid_value=50,
                                           deactivated=True))
        await crud.update_ticket(mk_ticket("SRC_REF", "EVS", "TT_S", paid_value=50,
                                           refunded=True))
        tgt.extra.promo_codes = [upgrade()]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC_DEAD"], one("TT_T1"))
        r2 = await calc(tgt, ["SRC_REF"], one("TT_T1"))
        assert approx(r.discount, 0) and approx(r2.discount, 0), (
            f"U8 deactivated/refunded sources rejected ({r.discount}/{r2.discount})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U9
def test_move_upgrade_refuses_multi_ticket_basket():
    async def run():
        src, tgt = await _setup()
        tgt.extra.promo_codes = [upgrade()]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC1"], one("TT_T1", qty=2))
        assert approx(r.discount, 0), (
            f"U9 move upgrade refuses a multi-ticket basket ({r.discount})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U10
def test_upgrade_and_friend_rules_coexist():
    async def run():
        src, tgt = await _setup()
        friend = friend_rule()
        tgt.extra.promo_codes = [upgrade(), friend]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC1"], one("TT_T2", qty=2))
        assert approx(r.discount, 60) and approx(r.total, 60), (
            f"U10 multiple ticket-source rules coexist ({r.discount}/{r.total})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U11
def test_chained_credit_uses_paid_value():
    async def run():
        src, tgt = await _setup()
        await crud.update_ticket(mk_ticket("SRC_CHAIN", "EVS", "TT_S", paid_value=150))
        tgt.extra.promo_codes = [upgrade()]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC_CHAIN"], one("TT_T1"))
        assert approx(r.discount, 150) and approx(r.total, 50), (
            f"U11 chained credit uses paid_value not face value ({r.discount}/{r.total})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U12
def test_move_consumption_voids_source_and_releases_seat():
    async def run():
        src, tgt = await _setup()
        friend = friend_rule()
        src.sold = 1
        await crud.update_event(src)
        tt_s = await crud.get_ticket_type("TT_S")
        tt_s.sold = 1
        await crud.update_ticket_type(tt_s)
        tgt.extra.promo_codes = [upgrade(), friend]
        await crud.update_event(tgt)
        match = await S._match_ticket_rule(tgt, "SRC1", 1)
        await S._consume_upgraded_source(match[0], match[1], "NEW_TKT")
        consumed = await crud.get_ticket("SRC1")
        src_after = await crud.get_event("EVS")
        tt_after = await crud.get_ticket_type("TT_S")
        assert (consumed.extra.deactivated and consumed.extra.upgraded_to == "NEW_TKT"
                and src_after.sold == 0 and tt_after.sold == 0), (
            f"U12 move voids the source and releases the seat "
            f"(deact={consumed.extra.deactivated} sold={src_after.sold}/{tt_after.sold})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U13
def test_registered_source_keeps_its_seat():
    async def run():
        src, tgt = await _setup()
        friend = friend_rule()
        src.sold = 1
        await crud.update_event(src)
        tt_s = await crud.get_ticket_type("TT_S")
        tt_s.sold = 1
        await crud.update_ticket_type(tt_s)
        tgt.extra.promo_codes = [upgrade(), friend]
        await crud.update_event(tgt)
        await crud.update_ticket(mk_ticket("SRC_REG", "EVS", "TT_S", paid_value=50,
                                           registered=True))
        match = await S._match_ticket_rule(tgt, "SRC_REG", 1)
        await S._consume_upgraded_source(match[0], match[1], "NEW2")
        src_after = await crud.get_event("EVS")
        assert src_after.sold == 1, (
            f"U13 attended/registered source keeps its seat (sold={src_after.sold})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U14
def test_same_event_source_with_unnamed_scope():
    async def run():
        src, tgt = await _setup()
        await crud.update_ticket(mk_ticket("SRC_SAME", "EVT", "TT_T2", paid_value=60))
        tgt.extra.promo_codes = [M.PromoCode(source=M.PromoSource(require_ticket=True),
                                             discount_fixed=10, combinable=False)]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC_SAME"], one("TT_T2"))
        assert approx(r.discount, 10) and approx(r.total, 50), (
            f"U14 same-event source works with an unnamed scope ({r.discount}/{r.total})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U15
def test_combinable_ticket_source_stacks_with_literal_code():
    async def run():
        src, tgt = await _setup()
        await crud.update_ticket(mk_ticket("SRC_STACK", "EVS", "TT_S", paid_value=50))
        combo = M.PromoCode(source=M.PromoSource(require_ticket=True, event_ids=["EVS"]),
                            discount_fixed=50, combinable=True)
        literal = M.PromoCode(code="EXTRA10", discount_percent=10, combinable=True)
        tgt.extra.promo_codes = [combo, literal]
        await crud.update_event(tgt)
        r = await calc(tgt, ["SRC_STACK", "EXTRA10"], one("TT_T1"))
        assert approx(r.discount, 65) and approx(r.total, 135), (
            f"U15 combinable ticket-source promo stacks with a literal code "
            f"({r.discount}/{r.total})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U16-U17
def test_ticket_redemption_reservation_and_shape_gate():
    # Regression for the ffcc559 gate bug: multi-ticket redemptions must still
    # be RESERVED, and max_tickets must refuse an oversized basket.
    async def run():
        src, tgt = await _setup()
        friend = friend_rule()
        await crud.update_ticket(mk_ticket("SRC_MULTI", "EVS", "TT_S", paid_value=50))
        await crud.update_ticket(mk_ticket("SRC_ONE", "EVS", "TT_S", paid_value=50))
        tgt.extra.promo_codes = [friend]
        await crud.update_event(tgt)
        await S._reserve_ticket_voucher(tgt, "SRC_MULTI", "BK_M", item_count=2)
        reserved = await crud.get_ticket("SRC_MULTI")
        assert len(reserved.extra.ticket_id_voucher_redemptions) == 1, (
            f"U16 multi-ticket redemption is reserved "
            f"({reserved.extra.ticket_id_voucher_redemptions})"
        )
        tgt.extra.promo_codes = [M.PromoCode(
            source=M.PromoSource(require_ticket=True, event_ids=["EVS"]),
            discount_percent=50, combinable=False, max_tickets=1)]
        await crud.update_event(tgt)
        with pytest.raises(ValueError):
            await S._reserve_ticket_voucher(tgt, "SRC_ONE", "BK_1", item_count=2)  # U17 max_tickets=1 refuses a 2-ticket basket

    asyncio.run(run())


# ---------------------------------------------------------------- U18
def test_activation_stamps_paid_value_from_basket_total():
    async def run():
        src, tgt = await _setup()
        await crud.update_ticket(mk_ticket("SRC_ACT", "EVS", "TT_S"))
        act_basket = M.Basket(id="BK_ACT", event_id="EVS", wallet="w1", email="", name="",
                              promo_codes=[], paid=False, total=42.0)
        await crud.create_basket(act_basket)
        act_ticket = await crud.get_ticket("SRC_ACT")
        act_ticket.basket_id = "BK_ACT"
        await crud.update_ticket(act_ticket)
        await S._activate_basket_tickets(act_basket, [act_ticket], src)
        refreshed = await crud.get_ticket("SRC_ACT")
        assert approx(refreshed.extra.paid_value, 42.0), (
            f"U18 activation stamps paid_value from the basket total "
            f"({refreshed.extra.paid_value})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- U19-U21
def test_backfill_paid_values():
    async def run():
        src, tgt = await _setup()
        await crud.create_basket(M.Basket(id="BK_BF", event_id="EVS", wallet="w1",
                                          email="", name="", promo_codes=[], paid=True,
                                          total=40.0))
        await crud.update_ticket(mk_ticket("SRC_B1", "EVS", "TT_S", basket_id="BK_BF"))
        await crud.update_ticket(mk_ticket("SRC_B2", "EVS", "TT_S", basket_id="BK_BF"))
        await crud.update_ticket(mk_ticket("SRC_NB", "EVS", "TT_S"))
        summary = await S.backfill_paid_values("w1")
        b1 = await crud.get_ticket("SRC_B1")
        nb = await crud.get_ticket("SRC_NB")
        before = (await crud.get_ticket("SRC1")).extra.paid_value
        assert approx(b1.extra.paid_value, 20.0), (
            f"U19 backfill splits a basket total across its tickets ({b1.extra.paid_value})"
        )
        assert approx(nb.extra.paid_value, 50.0), (
            f"U20 backfill falls back to the ticket type price ({nb.extra.paid_value})"
        )
        assert approx(before, 50.0) and summary["filled"] >= 3, (
            f"U21 backfill is idempotent (leaves existing values alone) "
            f"({before}/{summary})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- V1-V9
def test_offer_codes():
    # Offer codes additionally require a ticket id, which makes several
    # ticket-scoped offers identifiable to the buyer.
    async def run():
        src, tgt = await _setup()
        await crud.update_ticket(mk_ticket("SRC_V1", "EVS", "TT_S", paid_value=50))
        await crud.update_ticket(mk_ticket("SRC_V2", "EVS", "TT_S", paid_value=50))

        named = M.PromoCode(
            code="UPGRADE50",
            source=M.PromoSource(require_ticket=True, event_ids=["EVS"], move=True,
                                 credit="paid"),
            combinable=False, ticket_type_ids=["TT_T1"])
        tgt.extra.promo_codes = [named]
        await crud.update_event(tgt)

        # V1 the offer code alone is recognised and reports what it still needs
        r = await calc(tgt, ["UPGRADE50"], one("TT_T1"))
        assert (approx(r.discount, 0) and len(r.pending) == 1
                and r.pending[0].code == "UPGRADE50"
                and r.pending[0].requires == "ticket_id"), (
            "V1 offer code alone is pending (drives the auto-prompt) "
            f"(discount={r.discount} pending={[(p.code, p.requires) for p in r.pending]})"
        )

        # V2 code + ticket applies, and the applied code is the OFFER CODE
        r = await calc(tgt, ["UPGRADE50", "SRC_V1"], one("TT_T1"))
        assert (approx(r.discount, 50) and approx(r.total, 150)
                and [d.code for d in r.discounts_applied] == ["UPGRADE50"]), (
            f"V2 offer code + ticket applies the credit ({r.discount}/{r.total} "
            f"{[d.code for d in r.discounts_applied]})"
        )

        # V3 a ticket alone does not activate a coded offer
        r = await calc(tgt, ["SRC_V2"], one("TT_T1"))
        assert (approx(r.discount, 0)
                and [x.reason for x in r.rejections] == ["ticket_needs_offer_code"]), (
            "V3 a ticket alone cannot use a coded offer "
            f"({r.discount} {[(x.code, x.reason) for x in r.rejections]})"
        )

        # V4 an unknown token is explained, exactly once
        r = await calc(tgt, ["UPGRADE50", "NOTATOKEN"], one("TT_T1"))
        assert (approx(r.discount, 0)
                and [x.reason for x in r.rejections] == ["ticket_not_found"]), (
            "V4 an unknown token gets exactly one rejection reason "
            f"({[(x.code, x.reason) for x in r.rejections]})"
        )

        # V5 two named offers on one event, distinguished by the code typed
        await crud.update_ticket(mk_ticket("SRC_V5", "EVS", "TT_S", paid_value=50))
        friend2 = M.PromoCode(
            code="BRINGAFRIEND",
            source=M.PromoSource(require_ticket=True, event_ids=["EVS"]),
            discount_percent=50, combinable=False, max_tickets=1)
        tgt.extra.promo_codes = [named, friend2]
        await crud.update_event(tgt)
        r_up = await calc(tgt, ["UPGRADE50", "SRC_V5"], one("TT_T1"))
        r_fr = await calc(tgt, ["BRINGAFRIEND", "SRC_V5"], one("TT_T1"))
        assert (approx(r_up.discount, 50)
                and [d.code for d in r_up.discounts_applied] == ["UPGRADE50"]
                and approx(r_fr.discount, 100)
                and [d.code for d in r_fr.discounts_applied] == ["BRINGAFRIEND"]), (
            f"V5 multiple named offers are selected by code "
            f"(up={r_up.discount}{[d.code for d in r_up.discounts_applied]} "
            f"fr={r_fr.discount}{[d.code for d in r_fr.discounts_applied]})"
        )

        # V6 an exhausted SOURCE TICKET is refused with a specific reason
        await crud.update_ticket(mk_ticket("SRC_V6", "EVS", "TT_S", paid_value=50))
        await S._reserve_ticket_voucher(tgt, "SRC_V6", "BK_V6", item_count=1)
        r = await calc(tgt, ["UPGRADE50", "SRC_V6"], one("TT_T1"))
        assert (approx(r.discount, 0)
                and [x.reason for x in r.rejections] == ["ticket_redemptions_exhausted"]), (
            "V6 an exhausted source ticket is refused with a reason "
            f"({[(x.code, x.reason) for x in r.rejections]})"
        )

        # V8 a valid ticket that the BASKET SHAPE doesn't fit says so precisely
        r = await calc(tgt, ["BRINGAFRIEND", "SRC_V5"], two("TT_T1"))
        assert (approx(r.discount, 0)
                and [x.reason for x in r.rejections] == ["ticket_count_not_eligible"]), (
            "V8 basket-shape refusal gets its own reason, not a generic one "
            f"({[(x.code, x.reason) for x in r.rejections]})"
        )

        # V9 max_uses is now enforceable on a ticket rule (the code is what counts)
        await crud.update_ticket(mk_ticket("SRC_V7", "EVS", "TT_S", paid_value=50))
        limited = M.PromoCode(
            code="LIMITED",
            source=M.PromoSource(require_ticket=True, event_ids=["EVS"]),
            discount_fixed=10, combinable=False, max_uses=1, used_count=0)
        tgt.extra.promo_codes = [limited]
        await crud.update_event(tgt)
        r = await calc(tgt, ["LIMITED", "SRC_V7"], one("TT_T2"))
        await S._increment_promo_uses(tgt, r.discounts_applied)
        refreshed = await crud.get_event("EVT")
        limited_after = [p for p in refreshed.extra.promo_codes if p.code == "LIMITED"][0]
        r2 = await calc(refreshed, ["LIMITED", "SRC_V7"], one("TT_T2"))
        assert (approx(r.discount, 10) and limited_after.used_count == 1
                and approx(r2.discount, 0)
                and [x.reason for x in r2.rejections] == ["promo_uses_exhausted"]), (
            f"V9 max_uses counts and caps a ticket rule (first={r.discount} "
            f"used={limited_after.used_count} second={r2.discount} "
            f"{[(x.code, x.reason) for x in r2.rejections]})"
        )

    asyncio.run(run())


# ---------------------------------------------------------------- W1-W8
def _pc(**kw):
    return M.PromoCode(**kw)


def _rejects(**kw):
    try:
        _pc(**kw)
        return False
    except Exception:
        return True


def test_model_invariants():
    assert (_rejects(code="", discount_percent=10)
            and _pc(code="HELLO", discount_percent=10).code == "HELLO"), (
        "W1 a code is required when no ticket is involved"
    )

    assert _pc(code="", source=M.PromoSource(require_ticket=True)).code == "", (
        "W2 a blank code is allowed when a ticket is required"
    )

    legacy = _pc(code="TICKETID", type="ticket", discount_percent=10)
    assert legacy.source.require_ticket is True and legacy.code == "", (
        f"W3 legacy type='ticket' maps onto require_ticket, sentinel cleared "
        f"({legacy.source.require_ticket}/{legacy.code!r})"
    )

    interim = _pc(code="UPGRADE50", source={"kind": "ticket", "move": True})
    assert (interim.source.require_ticket is True and interim.source.move is True
            and interim.code == "UPGRADE50"), (
        f"W4 interim source.kind maps onto require_ticket ({interim.source}/{interim.code!r})"
    )

    coerced = _pc(code="PLAIN", source={"require_ticket": False, "move": True,
                                        "credit": "paid"})
    assert coerced.source.move is False and coerced.source.credit == "none", (
        f"W5 ticket-only flags are dropped when no ticket is involved ({coerced.source})"
    )

    assert (_rejects(code="X", source={"require_ticket": True, "credit": "maybe"})
            and _pc(code="X", source={"require_ticket": True,
                                      "credit": "paid"}).source.credit == "paid"), (
        "W6 source credit must be 'none' or 'paid'"
    )

    both = _pc(code="BOTH", discount_percent=20, discount_fixed=5)
    assert both.discount_fixed is None and both.discount_percent == 20, (
        f"W7 percent and fixed discount stay exclusive "
        f"({both.discount_percent}/{both.discount_fixed})"
    )

    capped = _pc(code="FIRST20", max_uses=20, used_count=0,
                 source=M.PromoSource(require_ticket=True))
    assert capped.max_uses == 20 and capped.source.require_ticket is True, (
        f"W8 max_uses and require_ticket now coexist ({capped.max_uses}/"
        f"{capped.source.require_ticket})"
    )
