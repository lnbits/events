"""Check-in bands: which colour to hand over, and the record of handing it over.

The two axes the door cares about: an ACCESS band is one per ticket, a ROLE band
(speaker, crew) is one per offer code — a speaker's code buys two tickets and
only one of the pair is the speaker.
"""
import asyncio
from datetime import datetime, timezone

import pytest

from events import crud
from events import models as M
from events import services as S

TODAY = datetime.now(timezone.utc).date().isoformat()
WEEKEND = "WKND"
ONEDAY = "DAY"
FRI = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)
SAT = datetime(2026, 11, 21, 18, 0, tzinfo=timezone.utc)


async def make_event(name="Bitfest", token="tok123"):
    ev = M.Event(
        id="EVB", wallet="w1", name=name, info="", canceled=False,
        event_start_date="2026-01-01", event_end_date="2026-12-31",
        currency="GBP", admin_email=None, allow_fiat=False, fiat_currency="GBP",
        amount_tickets=100, price_per_ticket=149, time=datetime.now(timezone.utc),
        sold=0, banner=None,
        extra=M.EventExtra(
            bands=[
                M.Band(id="white", name="White", label="Weekend", colour="#fff"),
                M.Band(id="purple", name="Purple", label="Fri 1 Day", colour="#74f"),
                M.Band(id="orange", name="Orange", label="Sat 1 Day", colour="#f80"),
                M.Band(id="yellow", name="Yellow", label="Speaker", colour="#fd0"),
            ],
            band_rules=[
                M.BandRule(band_ids=["white"], ticket_type_ids=[WEEKEND]),
                M.BandRule(band_ids=["purple"], ticket_type_ids=[ONEDAY], day="fri"),
                M.BandRule(band_ids=["orange"], ticket_type_ids=[ONEDAY], day="sat"),
                M.BandRule(
                    band_ids=["yellow"], per="redemption", promo_prefixes=["SPK-"]
                ),
            ],
            scanner_token=token,
        ),
    )
    await crud.create_event(ev)
    for tid, tname, price in (
        (WEEKEND, "Single - Weekend", 199),
        (ONEDAY, "Single - One Day Pass", 99),
    ):
        await crud.create_ticket_type(
            M.TicketType(
                id=tid, event_id="EVB", name=tname, price=price, max_tickets=500,
                available_from=TODAY, available_to="2026-12-31",
                sort_order=0, extra={},
            )
        )
    return ev


async def make_ticket(ticket_id, ticket_type_id, event="EVB", extra=None, basket=None):
    t = M.Ticket(
        id=ticket_id, wallet="w1", event=event, name="Holder", email="a@b.c",
        registered=False, paid=True, time=datetime.now(timezone.utc),
        reg_timestamp=None, ticket_type_id=ticket_type_id, basket_id=basket,
        extra=extra or M.TicketExtra(),
    )
    await crud.update_ticket(t)
    return t


def test_access_band_follows_type_and_day():
    async def run():
        ev = await make_event()
        weekend = await make_ticket("T1", WEEKEND)
        assert [b.id for b in S.resolve_bands(ev, weekend, [], FRI)[0]] == ["white"]
        assert [b.id for b in S.resolve_bands(ev, weekend, [], SAT)[0]] == ["white"]

        day = await make_ticket("T2", ONEDAY)
        # A one-day pass has no day of its own: the colour is the day it is used.
        assert [b.id for b in S.resolve_bands(ev, day, [], FRI)[0]] == ["purple"]
        assert [b.id for b in S.resolve_bands(ev, day, [], SAT)[0]] == ["orange"]
    asyncio.run(run())


def test_role_band_is_one_per_code_not_per_ticket():
    async def run():
        ev = await make_event()
        a = await make_ticket(
            "A", WEEKEND, basket="B1",
            extra=M.TicketExtra(applied_promo_code="SPK-AAAAAA"),
        )
        b = await make_ticket(
            "B", WEEKEND, basket="B1",
            extra=M.TicketExtra(applied_promo_code="SPK-AAAAAA"),
        )
        bands_a, _ = S.resolve_bands(ev, a, [b])
        assert [x.id for x in bands_a] == ["white", "yellow"], "speaker gets both"

        # Once handed over, the second ticket must not hand out another yellow.
        a.extra.bands_issued = ["white", "yellow"]
        bands_b, note = S.resolve_bands(ev, b, [a])
        assert [x.id for x in bands_b] == ["white"]
        assert "already issued" in note
    asyncio.run(run())


def test_checkin_records_the_hand_over_and_never_re_checks_in():
    async def run():
        ev = await make_event()
        await make_ticket("C1", WEEKEND)

        with pytest.raises(PermissionError):
            await S.checkin_view("C1", "wrong-token")
        with pytest.raises(ValueError):
            await S.checkin_view("NOPE", "tok123")

        first = await S.checkin_view("C1", "tok123", commit=True)
        assert first.already_checked_in is True
        assert first.event_name == "Bitfest", "the public page gets the name here"
        assert first.ticket.extra.bands_issued == ["white"]
        assert first.checked_in_at is not None

        # An override on the confirm records what was actually handed over.
        again = await S.checkin_view("C1", "tok123", commit=True, bands=["white", "yellow"])
        assert again.ticket.extra.bands_issued == ["white"], "no re-check-in"
        assert again.bands and [b.id for b in again.bands] == ["white"]
    asyncio.run(run())


def test_house_rules_match_the_band_scheme():
    async def run():
        types = [
            M.TicketType(id="WT", event_id="E", name="Single - Weekend", price=1,
                         max_tickets=1, available_from=TODAY, available_to=TODAY,
                         sort_order=0, extra={}),
            M.TicketType(id="OD", event_id="E", name="Single - One Day Pass", price=1,
                         max_tickets=1, available_from=TODAY, available_to=TODAY,
                         sort_order=0, extra={}),
            M.TicketType(id="NME", event_id="E", name="New Music Economy Concert", price=1,
                         max_tickets=1, available_from=TODAY, available_to=TODAY,
                         sort_order=0, extra={}),
        ]
        fest = M.EventExtra()
        event = M.Event(
            id="E", wallet="w1", name="Bitfest 2026", info="", canceled=False,
            event_start_date="2026-01-01", event_end_date="2026-12-31",
            currency="GBP", admin_email=None, allow_fiat=False, fiat_currency="GBP",
            amount_tickets=1, price_per_ticket=1, time=datetime.now(timezone.utc),
            sold=0, banner=None, extra=fest,
        )
        rules = S.default_band_rules(event, types)
        pairs = [(r.band_ids, r.ticket_type_ids, r.day, r.per) for r in rules]
        assert (["white"], ["WT"], None, "ticket") in pairs
        assert (["purple"], ["OD"], "fri", "ticket") in pairs
        assert (["orange"], ["OD"], "sat", "ticket") in pairs
        assert (["red"], ["NME"], None, "ticket") in pairs
        assert (["yellow"], None, None, "redemption") in pairs
        crew = [r for r in rules if r.band_ids == ["black"]]
        assert crew and crew[0].per == "redemption"
        assert crew[0].promo_codes == ["VOLUNTEER"], "crew buys with VOLUNTEER"

        expo = event.dict()
        expo["name"] = "Bitfest 2026 Expo"
        expo_event = M.Event(**{**expo, "extra": M.EventExtra()})
        expo_rules = S.default_band_rules(expo_event, types)
        assert (["white", "yellow"], ["WT", "OD", "NME"], None, "ticket") in [
            (r.band_ids, r.ticket_type_ids, r.day, r.per) for r in expo_rules
        ]
    asyncio.run(run())


def test_band_scheme_is_validated_server_side(monkeypatch):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from events import views_api as V

    async def run():
        ev = await make_event()

        async def fake_event(_id):
            return ev

        async def fake_update(event):
            return event

        async def fake_types(_id):
            return [SimpleNamespace(id=WEEKEND), SimpleNamespace(id=ONEDAY)]

        monkeypatch.setattr(V, "get_event", fake_event)
        monkeypatch.setattr(V, "update_event_crud", fake_update)
        monkeypatch.setattr(V, "get_ticket_types", fake_types)
        wallet = SimpleNamespace(wallet=SimpleNamespace(id="w1"))
        band = M.Band(id="white", name="White", label="Weekend", colour="#fff")

        async def expect_400(setup):
            with pytest.raises(HTTPException) as info:
                await V.api_update_bands("EVB", setup, wallet)
            assert info.value.status_code == 400, info.value.detail

        # a rule must name a band that exists
        await expect_400(M.BandSetup(bands=[band], rules=[M.BandRule(band_ids=["nope"], ticket_type_ids=[WEEKEND])]))
        # a rule must have a condition or it matches everything
        await expect_400(M.BandSetup(bands=[band], rules=[M.BandRule(band_ids=["white"])]))
        # ticket types must belong to this event
        await expect_400(M.BandSetup(bands=[band], rules=[M.BandRule(band_ids=["white"], ticket_type_ids=["GHOST"])]))
        # ids must be unique (they are the rule's keys)
        await expect_400(M.BandSetup(bands=[band, band], rules=[]))

        out = await V.api_update_bands(
            "EVB",
            M.BandSetup(bands=[band], rules=[M.BandRule(band_ids=["white"], ticket_type_ids=[WEEKEND])]),
            wallet,
        )
        assert out == {"bands": 1, "rules": 1}
        assert ev.extra.bands[0].id == "white"
        assert ev.extra.scanner_token, "saving the scheme also mints the scanner token"

    asyncio.run(run())


def test_seeded_scheme_saves_through_the_api(monkeypatch):
    """The editor saves what `seed_bands` produced -- role rules carry no
    ticket_type_ids, which used to 500 the endpoint outright."""
    from types import SimpleNamespace

    from events import views_api as V

    async def run():
        ev = await make_event()
        types = [
            M.TicketType(id=WEEKEND, event_id="EVB", name="Single - Weekend", price=1,
                         max_tickets=1, available_from=TODAY, available_to=TODAY,
                         sort_order=0, extra={}),
            M.TicketType(id=ONEDAY, event_id="EVB", name="Single - One Day Pass", price=1,
                         max_tickets=1, available_from=TODAY, available_to=TODAY,
                         sort_order=0, extra={}),
        ]
        ev.extra.bands = [b.model_copy() for b in S.DEFAULT_BANDS]
        ev.extra.band_rules = S.default_band_rules(ev, types)

        async def fake_event(_id):
            return ev

        async def fake_update(event):
            return event

        async def fake_types(_id):
            return types

        monkeypatch.setattr(V, "get_event", fake_event)
        monkeypatch.setattr(V, "update_event_crud", fake_update)
        monkeypatch.setattr(V, "get_ticket_types", fake_types)
        payload = M.BandSetup(bands=ev.extra.bands, rules=ev.extra.band_rules)
        out = await V.api_update_bands(
            "EVB", payload, SimpleNamespace(wallet=SimpleNamespace(id="w1"))
        )
        assert out["bands"] == len(ev.extra.bands) and out["rules"] == len(payload.rules)

    asyncio.run(run())


def test_one_role_band_per_person_across_orders():
    """A speaker can redeem twice into two orders: same code + same buyer must
    not hand out a second Yellow."""
    async def run():
        ev = await make_event()
        a = await make_ticket(
            "D1", WEEKEND, basket="B1",
            extra=M.TicketExtra(applied_promo_code="SPK-AAAAAA"),
        )
        b = await make_ticket(
            "D2", WEEKEND, basket="B2",
            extra=M.TicketExtra(applied_promo_code="SPK-AAAAAA"),
        )
        first, _ = S.resolve_bands(ev, a, [], FRI)
        assert [x.id for x in first] == ["white", "yellow"]
        a.extra.bands_issued = ["white", "yellow"]
        await crud.update_ticket(a)

        view = await S.checkin_view("D2", "tok123")
        assert [x.id for x in view.bands] == ["white"]
        assert "already issued" in view.note
    asyncio.run(run())


def test_two_codes_on_one_ticket_keep_both_role_bands():
    async def run():
        ev = await make_event()
        ev.extra.bands.append(M.Band(id="black", name="Black", label="Crew", colour="#000"))
        ev.extra.band_rules.append(
            M.BandRule(band_ids=["black"], per="redemption", promo_codes=["VOLUNTEER"])
        )
        t = await make_ticket(
            "E1", WEEKEND,
            extra=M.TicketExtra(applied_promo_code="VOLUNTEER,SPK-AAAAAA"),
        )
        bands, _ = S.resolve_bands(ev, t, [], FRI)
        assert [b.id for b in bands] == ["white", "yellow", "black"]
    asyncio.run(run())


def test_a_check_in_without_bands_is_still_a_check_in():
    """Not every event bands its guests: the arrival is the record that matters."""
    async def run():
        ev = await make_event()
        await make_ticket("F1", WEEKEND)
        view = await S.checkin_view("F1", "tok123", [], commit=True)
        assert view.already_checked_in is True
        assert view.ticket.extra.bands_issued == []
        assert view.bands == []

        await make_ticket("F2", WEEKEND)
        with pytest.raises(S.CheckinError):
            await S.checkin_view("F2", "tok123", ["ghost"], commit=True)

        # an event that defines no bands and no rules at all
        ev.extra.bands = []
        ev.extra.band_rules = []
        await crud.update_event(ev)
        await make_ticket("F3", WEEKEND)
        bandless = await S.checkin_view("F3", "tok123", commit=True)
        assert bandless.bands == []
        assert bandless.already_checked_in is True
        assert bandless.ticket.extra.bands_issued == []
    asyncio.run(run())


def test_a_legacy_registered_ticket_can_still_record_its_bands():
    """The old register endpoint set registered=True and recorded nothing; that
    ticket must still be able to record what it was handed, once."""
    async def run():
        ev = await make_event()
        t = await make_ticket("G1", WEEKEND)
        t.registered = True
        await crud.update_ticket(t)
        view = await S.checkin_view("G1", "tok123", ["white", "yellow"], commit=True)
        assert view.ticket.extra.bands_issued == ["white", "yellow"]
        again = await S.checkin_view("G1", "tok123", ["white"], commit=True)
        assert again.ticket.extra.bands_issued == ["white", "yellow"], "record is final"
    asyncio.run(run())


def test_concurrent_scans_issue_one_role_band():
    """Two staff, two phones, one speaker order: the lock must yield one Yellow."""
    async def run():
        ev = await make_event()
        a = await make_ticket("H1", WEEKEND, basket="B9",
                              extra=M.TicketExtra(applied_promo_code="SPK-AAAAAA"))
        b = await make_ticket("H2", WEEKEND, basket="B9",
                              extra=M.TicketExtra(applied_promo_code="SPK-AAAAAA"))
        await asyncio.gather(
            S.checkin_view("H1", "tok123", commit=True),
            S.checkin_view("H2", "tok123", commit=True),
        )
        stored = [t for t in (await crud.get_ticket("H1"), await crud.get_ticket("H2")) ]
        yellows = sum(1 for t in stored if "yellow" in (t.extra.bands_issued or []))
        assert yellows == 1, f"yellow issued {yellows}x"
    asyncio.run(run())


def test_every_weekday_can_be_named():
    """The door is not limited to Fri/Sat: any scan day can carry a rule."""
    async def run():
        ev = await make_event()
        thu = datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc)
        sun = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)
        assert S._checkin_day(thu) == "thu" and S._checkin_day(sun) == "sun"

        day_pass = await make_ticket("J1", ONEDAY)
        assert S.resolve_bands(ev, day_pass, [], thu)[0] == [], "no Thursday rule yet"
        ev.extra.band_rules.append(
            M.BandRule(band_ids=["purple"], ticket_type_ids=[ONEDAY], day="thu")
        )
        assert [b.id for b in S.resolve_bands(ev, day_pass, [], thu)[0]] == ["purple"]
        ev.extra.band_rules.append(
            M.BandRule(band_ids=["white"], ticket_type_ids=[ONEDAY], day="sun")
        )
        assert [b.id for b in S.resolve_bands(ev, day_pass, [], sun)[0]] == ["white"]
    asyncio.run(run())


def test_the_default_clock_is_the_servers_local_time():
    """No hardcoded UTC: an unqualified scan uses astimezone()."""
    assert S._checkin_day() == S.WEEKDAY_NAMES[datetime.now().astimezone().weekday()]


def test_the_recent_checkins_feed_is_shared_state():
    """The list every phone at the door reads: server-side, newest first."""
    async def run():
        await make_event()
        first = await make_ticket("K1", WEEKEND, extra=M.TicketExtra(bands_issued=["white"]))
        first.registered = True
        first.reg_timestamp = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)
        await crud.update_ticket(first)
        second = await make_ticket("K2", WEEKEND, extra=M.TicketExtra(bands_issued=["white", "yellow"]))
        second.registered = True
        second.reg_timestamp = datetime(2026, 11, 20, 19, 0, tzinfo=timezone.utc)
        await crud.update_ticket(second)
        await make_ticket("K3", WEEKEND)  # never checked in

        with pytest.raises(PermissionError):
            await S.recent_checkins("EVB", "wrong-token")

        rows = await S.recent_checkins("EVB", "tok123")
        assert [r.id for r in rows] == ["K2", "K1"], "newest first, unchecked omitted"
        assert [b.name for b in rows[0].bands] == ["White", "Yellow"]
        assert rows[0].ticket_type_name == "Single - Weekend"
        assert len(await S.recent_checkins("EVB", "tok123", limit=1)) == 1
    asyncio.run(run())


def test_a_role_band_needs_an_access_band():
    """A code alone must not band someone: an add-on with a speaker code used to
    hand out Yellow with no admission behind it (and a guest could hold it)."""
    async def run():
        ev = await make_event()
        # a type with no rule at all, bought with a speaker code
        await crud.create_ticket_type(
            M.TicketType(id="ADDON", event_id="EVB", name="Screening seat", price=0,
                         max_tickets=50, available_from=TODAY, available_to="2026-12-31",
                         sort_order=0, extra={})
        )
        addon = await make_ticket(
            "L1", "ADDON", extra=M.TicketExtra(applied_promo_code="SPK-AAAAAA")
        )
        assert S.resolve_bands(ev, addon, [], FRI)[0] == [], "no admission, no bands"

        # the same code on a ticket that DOES admit still yields both
        weekend = await make_ticket(
            "L2", WEEKEND, extra=M.TicketExtra(applied_promo_code="SPK-AAAAAA")
        )
        assert [b.id for b in S.resolve_bands(ev, weekend, [], FRI)[0]] == ["white", "yellow"]

        # and an add-on attached to a weekend order still gives nothing on its own
        ev.extra.band_rules.append(
            M.BandRule(band_ids=["black"], per="redemption", promo_codes=["VOLUNTEER"])
        )
        crew_addon = await make_ticket(
            "L3", "ADDON", extra=M.TicketExtra(applied_promo_code="VOLUNTEER")
        )
        assert S.resolve_bands(ev, crew_addon, [], FRI)[0] == []
    asyncio.run(run())
