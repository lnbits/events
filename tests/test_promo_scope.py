"""PromoCode.ticket_type_ids scoping, ported from the standalone
``test_scope.py`` suite: 11 assertions (T1-T11).
"""
import asyncio
from datetime import datetime, timezone

from events import crud
from events import models as M
from events import services as S

TODAY = datetime.now(timezone.utc).date().isoformat()
# Ticket types mirroring BitFest 2026 prices
TB = {"TT_A": 149.0, "TT_B": 99.0, "TT_C": 35.0}


def approx(a, b, tol=0.011):
    return abs(a - b) <= tol


def one(tid, qty=1):
    return [{"ticket_type_id": tid, "quantity": qty}]


def make_event(extra_static, ev_id="EVX"):
    return M.Event(
        id=ev_id, wallet="w1", name="ScopeTest", info="", canceled=False,
        event_start_date="2026-01-01", event_end_date="2026-12-31",
        currency="GBP", admin_email=None, allow_fiat=False, fiat_currency="GBP",
        amount_tickets=1000, price_per_ticket=100, time=datetime.now(timezone.utc),
        sold=0, banner=None,
        extra=M.EventExtra(promo_codes=list(extra_static)))


async def seed(ev):
    await crud.create_event(ev)
    for tid, price in TB.items():
        await crud.create_ticket_type(
            M.TicketType(id=tid, event_id=ev.id, name=tid, price=price,
                         available_from=TODAY, available_to="2026-12-31"))
    return ev


async def calc(ev, codes, items):
    return await S.calculate_basket_total(ev, items, codes)


def _promos():
    return [
        # fixed 50, scoped to TT_A, non-combinable, cap 10
        M.PromoCode(code="LATERBIRD", discount_fixed=50, ticket_type_ids=["TT_A"],
                    combinable=False, max_uses=10),
        M.PromoCode(code="FIX50C", discount_fixed=50, ticket_type_ids=["TT_A"],
                    combinable=True),
        M.PromoCode(code="BASE21", discount_percent=21, ticket_type_ids=["TT_A"],
                    combinable=True),
        M.PromoCode(code="CAP50", discount_fixed=50, ticket_type_ids=["TT_C"],
                    combinable=True),
        M.PromoCode(code="ALL10", discount_percent=10, combinable=True),
        M.PromoCode(code="ALLFIX20", discount_fixed=20, combinable=True),
    ]


async def _seeded_event():
    return await seed(make_event(_promos()))


def test_scoped_fixed_discount():
    async def run():
        ev = await _seeded_event()
        r = await calc(ev, ["LATERBIRD"], one("TT_A"))
        assert approx(r.discount, 50) and approx(r.total, 99), (
            f"T1 scoped code discounts its base by 50 (disc={r.discount} total={r.total})"
        )
        r = await calc(ev, ["LATERBIRD"], one("TT_B"))
        assert approx(r.discount, 0) and approx(r.total, 99), (
            f"T2 out-of-scope basket gives no discount (disc={r.discount})"
        )
        r = await calc(ev, ["LATERBIRD"], [{"ticket_type_id": "TT_A", "quantity": 1},
                                           {"ticket_type_id": "TT_B", "quantity": 1}])
        assert approx(r.discount, 50) and approx(r.total, 198), (
            f"T3 mixed basket: 50 off, rest full price (disc={r.discount} total={r.total})"
        )
        r = await calc(ev, ["LATERBIRD"], one("TT_A", qty=2))
        assert approx(r.discount, 50) and approx(r.total, 248.0), (
            f"T4 qty=2 scoped base 298 -> 50 off (total={r.total})"
        )

    asyncio.run(run())


def test_fixed_capped_at_scoped_base():
    async def run():
        ev = await _seeded_event()
        r = await calc(ev, ["CAP50"], one("TT_C"))
        assert approx(r.discount, 35) and approx(r.total, 0), (
            f"T5 fixed discount capped at scoped base (disc={r.discount} total={r.total})"
        )

    asyncio.run(run())


def test_combinable_ordering():
    # ORDERING: scoped base first, then basket-wide on what remains.
    # FIX50C: 149 -> 99 remaining; ALL10: 10% of 99 = 9.9 -> 59.9 total discount.
    # A fixed+percent mix is required to actually prove the ordering.
    async def run():
        ev = await _seeded_event()
        r = await calc(ev, ["FIX50C", "ALL10"], one("TT_A"))
        assert approx(r.discount, 59.9) and approx(r.total, 89.1), (
            f"T6 combinable: base first then basket-wide (disc={r.discount} total={r.total})"
        )
        r = await calc(ev, ["LATERBIRD", "ALL10"], one("TT_A"))
        assert len(r.discounts_applied) == 1, (
            "T7 non-combinable scoped blocks basket-wide"
        )

    asyncio.run(run())


def test_scoped_absent_type_is_noop():
    async def run():
        ev = await _seeded_event()
        r = await calc(ev, ["LATERBIRD", "CAP50"], one("TT_A"))
        assert approx(r.discount, 50), (
            f"T8 scoped code on absent type is a no-op (disc={r.discount})"
        )

    asyncio.run(run())


def test_basket_wide_percent_regression():
    async def run():
        ev = await _seeded_event()
        r = await calc(ev, ["ALL10"], [{"ticket_type_id": "TT_A", "quantity": 1},
                                       {"ticket_type_id": "TT_B", "quantity": 1}])
        assert approx(r.discount, 24.8) and approx(r.total, 223.2), (
            f"T9 basket-wide percent unchanged (disc={r.discount})"
        )
        r = await calc(ev, ["BASE21", "ALLFIX20"], one("TT_A"))
        # BASE21: 149*0.21 = 31.29 -> 117.71 ; ALLFIX20: 20 -> 51.29
        assert approx(r.discount, 51.29), (
            f"T10 scoped percent then basket fixed (disc={r.discount})"
        )

    asyncio.run(run())


def test_scoped_code_respects_max_uses():
    async def run():
        ev2 = await seed(make_event(
            [M.PromoCode(code="MAXED", discount_fixed=50, ticket_type_ids=["TT_A"],
                         combinable=False, max_uses=1, used_count=1)], ev_id="EVY"))
        r = await calc(ev2, ["MAXED"], one("TT_A"))
        assert approx(r.discount, 0), f"T11 scoped code respects max_uses (disc={r.discount})"

    asyncio.run(run())
