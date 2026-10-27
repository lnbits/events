import asyncio
import inspect
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from lnbits import wallets
from lnbits.core import migrations as core_migrations
from lnbits.core.crud import (
    create_account,
    create_wallet,
    get_payments,
    get_standalone_payment,
    get_wallet,
)
from lnbits.core.db import db as core_db
from lnbits.core.helpers import run_migration
from lnbits.core.models import CreateInvoice, KeyType
from lnbits.core.services import (
    create_payment_request,
    pay_invoice,
    update_wallet_balance,
)
from lnbits.core.services import lnurl as core_lnurl
from lnbits.db import Database
from lnbits.settings import settings
from lnbits.task_manager import task_manager
from lnbits.wallets.fake import FakeWallet
from lnurl import encode

from .. import crud, migrations, services, tasks, views_api
from ..models import (
    CreateEvent,
    Event,
    EventExtra,
    PromoCode,
    Ticket,
    TicketExtra,
    TicketRefund,
)


@pytest.fixture
def event():
    today = datetime.now(timezone.utc)
    return Event(
        id="event",
        wallet="wallet",
        name="Event",
        info="**Welcome**",
        closing_date=(today + timedelta(days=1)).date().isoformat(),
        event_start_date=today.date().isoformat(),
        event_end_date=today.date().isoformat(),
        currency="sat",
        amount_tickets=10,
        price_per_ticket=1000,
        time=today,
        extra=EventExtra(
            promo_codes=[PromoCode(code="invite", discount_percent=50)],
            notification_body="Organiser message",
        ),
    )


@pytest_asyncio.fixture
async def database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "lnbits_data_folder", str(tmp_path))
    db = Database("ext_events")
    monkeypatch.setattr(crud, "db", db)
    for name, migrate in inspect.getmembers(migrations, inspect.isfunction):
        if name.startswith("m"):
            await migrate(db)
    yield db
    await db.engine.dispose()


@pytest_asyncio.fixture
async def payment_database(database, monkeypatch):
    db = Database("database")
    # Core modules share this database object; point it at the temporary database.
    for name in ("engine", "path", "lock"):
        monkeypatch.setattr(core_db, name, getattr(db, name))
    backend = FakeWallet()
    monkeypatch.setattr(wallets, "funding_source", backend)
    monkeypatch.setattr(settings, "lnbits_only_allow_incoming_payments", False)
    monkeypatch.setattr(settings, "lnbits_service_fee", 0)
    monkeypatch.setattr(settings, "lnbits_exchange_rate_providers", [])
    monkeypatch.setattr(task_manager, "tasks", [])
    monkeypatch.setattr(task_manager, "internal_invoice_queue", asyncio.Queue())
    async with core_db.connect() as conn:
        await run_migration(conn, core_migrations, "core")
    yield backend
    pending_tasks = [task.task for task in task_manager.tasks]
    for task in pending_tasks:
        task.cancel()
    await asyncio.gather(*pending_tasks, return_exceptions=True)
    await db.engine.dispose()


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        views_api,
        "get_user",
        AsyncMock(return_value=SimpleNamespace(wallet_ids=["wallet"])),
    )
    app = FastAPI()
    app.include_router(views_api.events_api_router, prefix="/events")
    app.include_router(views_api.tickets_api_router, prefix="/events")
    return app


def authorize(app, key_type):
    wallet = SimpleNamespace(id="wallet", user="user", inkey="merchant-key")
    info = SimpleNamespace(key_type=key_type, wallet=wallet)

    async def get_info():
        return info

    app.dependency_overrides[views_api.require_invoice_key] = get_info
    app.dependency_overrides[views_api.require_admin_key] = get_info


@pytest.mark.asyncio
@pytest.mark.parametrize("key_type", [KeyType.invoice, KeyType.admin])
@pytest.mark.parametrize("all_wallets", [False, True])
async def test_event_listing(app, event, monkeypatch, key_type, all_wallets):
    authorize(app, key_type)
    get_events = AsyncMock(return_value=[event])
    monkeypatch.setattr(views_api, "get_events", get_events)
    monkeypatch.setattr(
        views_api,
        "get_user",
        AsyncMock(return_value=SimpleNamespace(wallet_ids=["wallet", "second"])),
    )
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.get(f"/events/api/v1/events?all_wallets={all_wallets}")
    assert response.status_code == 200
    extra = response.json()[0]["extra"]
    assert ("promo_codes" in extra) == (key_type == KeyType.admin)
    assert ("notification_body" in extra) == (key_type == KeyType.admin)
    get_events.assert_awaited_once_with(
        ["wallet", "second"] if all_wallets else ["wallet"]
    )


@pytest.mark.asyncio
async def test_public_event_is_read_only(app, event, monkeypatch):
    monkeypatch.setattr(views_api, "get_event", AsyncMock(return_value=event))
    update = AsyncMock()
    refund = AsyncMock()
    monkeypatch.setattr(views_api, "update_event", update)
    monkeypatch.setattr(views_api, "refund_tickets", refund)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.get("/events/api/v1/events/event")
        assert response.status_code == 200
        assert "promo_codes" not in response.json()["extra"]
        event.closing_date = "2000-01-01"
        event.extra.conditional = True
        response = await client.get("/events/api/v1/events/event")
        assert response.status_code == 410
    update.assert_not_awaited()
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_wallet_binding(app, event, monkeypatch):
    authorize(app, KeyType.admin)
    create = AsyncMock(return_value=event)
    monkeypatch.setattr(views_api, "create_event", create)
    data = CreateEvent(**event.dict()).dict()
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        data["wallet"] = "other"
        assert (
            await client.post("/events/api/v1/events", json=data)
        ).status_code == 403
        create.assert_not_awaited()
        data["wallet"] = "wallet"
        assert (
            await client.post("/events/api/v1/events", json=data)
        ).status_code == 200


@pytest.mark.asyncio
async def test_ticket_registration(app, database):
    ticket = await crud.create_ticket(
        "ticket",
        "wallet",
        "event",
        "Buyer",
        "buyer@example.com",
        {"refund_address": "private"},
    )
    ticket.paid = True
    await crud.update_ticket(ticket)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        wrong = await client.put(
            "/events/api/v1/tickets/register/ticket?event_id=other"
        )
        assert wrong.status_code == 403
        responses = await asyncio.gather(
            *[
                client.put("/events/api/v1/tickets/register/ticket?event_id=event")
                for _ in range(2)
            ]
        )
    assert sum(r.status_code == 200 for r in responses) == 1
    result = next(r.json() for r in responses if r.status_code == 200)
    assert result["registered"] is True
    assert result["id"] == ticket.id
    assert "email" not in result and "extra" not in result and "wallet" not in result


@pytest.mark.asyncio
async def test_refund_invoice_assignment(database):
    first = TicketRefund(id="ticket", payment_hash="hash", payment_request="invoice")
    second = TicketRefund(id="ticket", payment_hash="other", payment_request="other")
    results = await asyncio.gather(
        crud.create_ticket_refund(first), crud.create_ticket_refund(second)
    )
    assert results[0] == results[1]
    duplicate = TicketRefund(
        id="another",
        payment_hash=results[0].payment_hash,
        payment_request=results[0].payment_request,
    )
    with pytest.raises(ValueError, match="already assigned"):
        await crud.create_ticket_refund(duplicate)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["pending", "failed", "exception"])
async def test_refund_completion(database, monkeypatch, state):
    ticket = await crud.create_ticket(
        "ticket",
        "wallet",
        "event",
        "Buyer",
        "buyer@example.com",
        {"refund_address": "buyer@example.com", "sats_paid": 1000},
    )
    ticket.paid = True
    await crud.update_ticket(ticket)
    fetch = AsyncMock(return_value="invoice")
    monkeypatch.setattr(services, "get_pr_from_lnurl", fetch)
    monkeypatch.setattr(
        services, "bolt11_decode", lambda _: SimpleNamespace(payment_hash="hash")
    )
    monkeypatch.setattr(
        services, "get_standalone_payment", AsyncMock(return_value=None)
    )
    payment = SimpleNamespace(success=False, failed=state == "failed")
    pay = AsyncMock(return_value=payment)
    if state == "exception":
        pay.side_effect = RuntimeError("uncertain outcome")
    monkeypatch.setattr(services, "pay_invoice", pay)
    await services.refund_tickets("event")
    fetch.assert_awaited_once_with("buyer@example.com", 1000000)
    pay.assert_awaited_once_with(
        wallet_id="wallet",
        payment_request="invoice",
        max_sat=1000,
        tag="events_refund",
        extra={"ticket_id": "ticket"},
    )
    stored = await crud.get_ticket("ticket")
    assert stored
    assert not stored.extra.refunded
    assert await crud.get_ticket_refund("ticket") is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["pending", "failed"])
async def test_existing_refund_is_reconciled(database, monkeypatch, state):
    ticket = await crud.create_ticket(
        "ticket",
        "wallet",
        "event",
        "Buyer",
        "buyer@example.com",
        {"refund_address": "buyer@example.com", "sats_paid": 1000},
    )
    ticket.paid = True
    await crud.update_ticket(ticket)
    await crud.create_ticket_refund(
        TicketRefund(id="ticket", payment_hash="hash", payment_request="invoice")
    )
    payment = SimpleNamespace(
        is_out=True,
        success=False,
        failed=state == "failed",
        extra={"ticket_id": "ticket"},
    )
    monkeypatch.setattr(
        services, "get_standalone_payment", AsyncMock(return_value=payment)
    )
    monkeypatch.setattr(
        services, "update_pending_payment", AsyncMock(return_value=payment)
    )
    pay = AsyncMock()
    fetch = AsyncMock()
    monkeypatch.setattr(services, "pay_invoice", pay)
    monkeypatch.setattr(services, "get_pr_from_lnurl", fetch)
    await services.refund_tickets("event")
    pay.assert_not_awaited()
    fetch.assert_not_awaited()
    stored = await crud.get_ticket("ticket")
    assert stored
    assert not stored.extra.refunded


@pytest.mark.asyncio
async def test_refund_resumes_after_interruption(database, monkeypatch):
    ticket = await crud.create_ticket(
        "ticket",
        "wallet",
        "event",
        "Buyer",
        "buyer@example.com",
        {"refund_address": "buyer@example.com", "sats_paid": 1000},
    )
    ticket.paid = True
    await crud.update_ticket(ticket)
    fetch = AsyncMock(return_value="invoice")
    pay = AsyncMock(side_effect=TimeoutError("Payment outcome unknown"))
    pending = SimpleNamespace(
        is_out=True, success=False, extra={"ticket_id": ticket.id}
    )
    reconcile = AsyncMock(return_value=SimpleNamespace(success=True, failed=False))
    monkeypatch.setattr(services, "get_pr_from_lnurl", fetch)
    monkeypatch.setattr(
        services, "bolt11_decode", lambda _: SimpleNamespace(payment_hash="hash")
    )
    monkeypatch.setattr(services, "pay_invoice", pay)
    monkeypatch.setattr(
        services, "get_standalone_payment", AsyncMock(side_effect=[None, pending])
    )
    monkeypatch.setattr(services, "update_pending_payment", reconcile)

    await services.refund_tickets("event")
    stored = await crud.get_ticket(ticket.id)
    assert stored and not stored.extra.refunded
    refund = await crud.get_ticket_refund(ticket.id)
    assert refund and refund.payment_request == "invoice"

    await services.refund_tickets("event")
    fetch.assert_awaited_once()
    pay.assert_awaited_once()
    reconcile.assert_awaited_once_with(pending)
    stored = await crud.get_ticket(ticket.id)
    assert stored and stored.extra.refunded
    assert await crud.get_ticket_refund(ticket.id) == refund


@pytest.mark.asyncio
async def test_close_events(event, monkeypatch):
    event.closing_date = "2000-01-01"
    event.extra.conditional = True
    monkeypatch.setattr(services, "get_closed_events", AsyncMock(return_value=[event]))
    update = AsyncMock()
    refund = AsyncMock(return_value=True)
    monkeypatch.setattr(services, "update_event", update)
    monkeypatch.setattr(services, "refund_tickets", refund)
    mark = AsyncMock()
    monkeypatch.setattr(services, "mark_event_closed", mark)
    await services.close_events()
    assert event.canceled
    update.assert_awaited_once_with(event)
    refund.assert_awaited_once_with(event.id)
    mark.assert_awaited_once_with(event)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("days_ago", "conditional", "sold", "canceled"),
    [
        (0, True, 0, False),
        (1, True, 5, False),
        (1, False, 0, False),
        (1, False, 0, True),
    ],
    ids=["closing-today", "minimum-met", "unconditional", "already-canceled"],
)
async def test_close_events_boundaries(
    event, monkeypatch, days_ago, conditional, sold, canceled
):
    event.closing_date = (
        datetime.now(timezone.utc).date() - timedelta(days=days_ago)
    ).isoformat()
    event.extra.conditional = conditional
    event.extra.min_tickets = 5
    event.sold = sold
    event.canceled = canceled
    monkeypatch.setattr(services, "get_closed_events", AsyncMock(return_value=[event]))
    update = AsyncMock()
    refund = AsyncMock(return_value=True)
    monkeypatch.setattr(services, "update_event", update)
    monkeypatch.setattr(services, "refund_tickets", refund)
    monkeypatch.setattr(services, "purge_unpaid_tickets", AsyncMock())
    monkeypatch.setattr(services, "get_event_tickets", AsyncMock(return_value=[]))
    monkeypatch.setattr(services, "mark_event_closed", AsyncMock())

    await services.close_events()

    assert event.canceled == canceled
    update.assert_not_awaited()
    if canceled:
        refund.assert_awaited_once_with(event.id)
    else:
        refund.assert_not_awaited()


def test_notification_urls(event, monkeypatch):
    monkeypatch.setattr(settings, "lnbits_baseurl", "https://example.com")
    ticket = Ticket(
        id="ticket",
        wallet="wallet",
        event=event.id,
        name="Buyer",
        email="buyer@example.com",
        registered=False,
        paid=True,
        time=event.time,
        reg_timestamp=event.time,
        extra=TicketExtra.parse_obj(
            {
                "ticket_base_url": "https://untrusted.example",
                "ticket_wave_id": "primary",
            }
        ),
    )
    assert "ticket_base_url" not in ticket.extra.dict()
    assert services._ticket_url(ticket) == "https://example.com/events/ticket/ticket"
    event.extra.ticket_waves = services.ensure_ticket_waves(event)
    event.extra.ticket_waves[0].use_ticket_image = True
    assert (
        services._ticket_image_url(ticket, event)
        == "https://example.com/events/api/v1/qr/ticket"
    )


@pytest.mark.asyncio
async def test_refund_destination_policy(database, monkeypatch):
    monkeypatch.setattr(settings, "lnbits_lnurl_allow_private_ips", False)
    ticket = await crud.create_ticket(
        "ticket",
        "wallet",
        "event",
        "Buyer",
        "buyer@example.com",
        {"refund_address": str(encode("http://127.0.0.1/private")), "sats_paid": 1000},
    )
    ticket.paid = True
    await crud.update_ticket(ticket)
    send = AsyncMock()
    pay = AsyncMock()
    monkeypatch.setattr(core_lnurl, "_send_lnurl_request", send)
    monkeypatch.setattr(services, "pay_invoice", pay)
    await services.refund_tickets("event")
    send.assert_not_awaited()
    pay.assert_not_awaited()
    assert await crud.get_ticket_refund("ticket") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("internal", [True, False], ids=["internal", "fake-backend"])
async def test_refund_payment_flow(payment_database, app, event, monkeypatch, internal):
    account = await create_account()
    organiser = await create_wallet(user_id=account.id)
    buyer_account = await create_account()
    buyer = await create_wallet(user_id=buyer_account.id)
    await update_wallet_balance(buyer, 2000)
    data = CreateEvent(**event.dict())
    data.wallet = organiser.id
    event = await crud.create_event(data)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/events/api/v1/tickets/{event.id}",
            json={
                "name": "Buyer",
                "email": "buyer@example.com",
                "refund_address": str(encode("https://1.1.1.1/refund")),
            },
        )
    assert response.status_code == 200
    purchase = response.json()
    await pay_invoice(wallet_id=buyer.id, payment_request=purchase["payment_request"])
    incoming = await get_standalone_payment(
        purchase["payment_hash"], incoming=True, wallet_id=organiser.id
    )
    assert incoming and incoming.success
    await tasks.on_invoice_paid(incoming)
    ticket = await crud.get_ticket(purchase["payment_hash"])
    assert ticket and ticket.paid
    paid_event = await crud.get_event(event.id)
    assert paid_event and paid_event.sold == 1 and paid_event.amount_tickets == 9
    if internal:
        invoice = await create_payment_request(buyer.id, CreateInvoice(amount=1000))
        payment_request = invoice.bolt11
        payment_hash = invoice.payment_hash
    else:
        response = await payment_database.create_invoice(amount=1000)
        assert response.ok and response.payment_request and response.checking_id
        payment_request = response.payment_request
        payment_hash = response.checking_id

    async def lnurl_response(url, **kwargs):
        if url.path == "/refund":
            payload = {
                "tag": "payRequest",
                "callback": "https://1.1.1.1/invoice",
                "minSendable": 1000000,
                "maxSendable": 1000000,
                "metadata": '[["text/plain","Ticket refund"]]',
            }
        else:
            assert url.path == "/invoice"
            assert url.params["amount"] == "1000000"
            payload = {"pr": payment_request, "routes": []}
        return 200, {}, json.dumps(payload).encode()

    monkeypatch.setattr(core_lnurl, "_send_lnurl_request", lnurl_response)

    async def organiser_key():
        return SimpleNamespace(key_type=KeyType.admin, wallet=organiser)

    app.dependency_overrides[views_api.require_admin_key] = organiser_key
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(
            client.put(f"/events/api/v1/events/{event.id}/cancel"),
            client.put(f"/events/api/v1/events/{event.id}/cancel"),
        )
    assert all(response.status_code == 200 for response in responses)
    if not internal:
        stored = await crud.get_ticket(ticket.id)
        assert stored and not stored.extra.refunded
        refund = await crud.get_ticket_refund(ticket.id)
        assert refund and refund.payment_hash == payment_hash
        assert await get_payments(wallet_id=organiser.id, outgoing=True) == []
        await services.close_events()
        waiting = await crud.get_event(event.id)
        assert waiting and not waiting.close_processed
        # External payments need a routing reserve, even when the final fee is zero.
        funded_organiser = await get_wallet(organiser.id)
        assert funded_organiser
        await update_wallet_balance(funded_organiser, 100)
    await services.close_events()

    stored = await crud.get_ticket(ticket.id)
    assert stored and stored.extra.refunded
    closed = await crud.get_event(event.id)
    assert closed and closed.close_processed
    assert await crud.get_closed_events() == []
    refund = await crud.get_ticket_refund(ticket.id)
    assert refund and refund.payment_hash == payment_hash
    payments = await get_payments(wallet_id=organiser.id, outgoing=True)
    assert len(payments) == 1
    payment = payments[0]
    assert payment.success and payment.payment_hash == payment_hash
    assert payment.amount == -1000000
    assert payment.extra["ticket_id"] == ticket.id
    organiser_after = await get_wallet(organiser.id)
    buyer_after = await get_wallet(buyer.id)
    assert organiser_after and organiser_after.balance == (0 if internal else 100)
    assert buyer_after and buyer_after.balance == (2000 if internal else 1000)
    if not internal:
        assert payment_hash in payment_database.paid_invoices


@pytest.mark.asyncio
async def test_close_events_isolates_failures(event, monkeypatch):
    event.canceled = True
    following = event.copy(update={"id": "following"})
    monkeypatch.setattr(
        services, "get_closed_events", AsyncMock(return_value=[event, following])
    )
    refund = AsyncMock(side_effect=[RuntimeError("database unavailable"), True])
    mark = AsyncMock()
    warning = Mock()
    monkeypatch.setattr(services, "refund_tickets", refund)
    monkeypatch.setattr(services, "mark_event_closed", mark)
    monkeypatch.setattr(services.logger, "warning", warning)
    await services.close_events()
    assert refund.await_count == 2
    mark.assert_awaited_once_with(following)
    assert "RuntimeError: database unavailable" in warning.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("conditional", [False, True])
async def test_closed_event_cleanup(database, event, conditional):
    data = CreateEvent(**event.dict())
    data.closing_date = "2000-01-01"
    data.extra.conditional = conditional
    data.extra.min_tickets = 1
    closed = await crud.create_event(data)
    closed.sold = 1
    await crud.update_event(closed)
    for ticket_id in ("expired", "recent", "paid"):
        ticket = await crud.create_ticket(
            ticket_id, closed.wallet, closed.id, "Buyer", "buyer@example.com", {}
        )
        ticket.paid = ticket_id == "paid"
        if ticket_id == "expired":
            ticket.time -= timedelta(days=2)
        await crud.update_ticket(ticket)

    await services.close_events()
    assert await crud.get_ticket("expired") is None
    recent = await crud.get_ticket("recent")
    assert recent and not recent.paid
    assert await crud.get_ticket("paid") is not None
    stored = await crud.get_event(closed.id)
    assert stored and not stored.canceled and not stored.close_processed

    recent.time -= timedelta(days=2)
    await crud.update_ticket(recent)
    await services.close_events()
    assert await crud.get_ticket("recent") is None
    stored = await crud.get_event(closed.id)
    assert stored and stored.close_processed
    assert await crud.get_closed_events() == []

    late = await crud.create_ticket(
        "late", closed.wallet, closed.id, "Buyer", "buyer@example.com", {}
    )
    await services.set_ticket_paid(late)
    # A stale completion attempt must not hide a newly paid ticket.
    await crud.mark_event_closed(stored)
    reopened = await crud.get_event(closed.id)
    assert reopened and not reopened.close_processed
    assert len(await crud.get_closed_events()) == 1


@pytest.mark.asyncio
async def test_closed_event_update_reopens_processing(database, app, event):
    closed = await crud.create_event(CreateEvent(**event.dict()))
    closed.close_processed = True
    await crud.update_event(closed)
    authorize(app, KeyType.admin)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.put(
            f"/events/api/v1/events/{closed.id}",
            json=CreateEvent(**closed.dict()).dict(),
        )
    assert response.status_code == 200
    stored = await crud.get_event(closed.id)
    assert stored and not stored.close_processed


@pytest.mark.asyncio
async def test_closing_task_restarts(monkeypatch):
    close = AsyncMock(
        side_effect=[RuntimeError("temporary failure"), asyncio.CancelledError()]
    )
    monkeypatch.setattr(tasks, "close_events", close)
    monkeypatch.setattr(settings, "lnbits_running", True)
    with pytest.raises(asyncio.CancelledError):
        await task_manager._catch_everything_and_restart(
            tasks.close_expired_events, restart_interval=0
        )
    assert close.await_count == 2


@pytest.mark.parametrize(
    "base_url", ["", "/relative", "ftp://example.com", "https://example.com/?x=1"]
)
def test_event_base_url_validation(monkeypatch, base_url):
    monkeypatch.setattr(settings, "lnbits_baseurl", base_url)
    with pytest.raises(ValueError, match="LNBITS_BASEURL"):
        services.get_event_base_url()


@pytest.mark.asyncio
@pytest.mark.parametrize("base_url", ["", "https://tickets.example/lnbits/"])
@pytest.mark.parametrize("reference", ["onchain-wallet", "core:onchain-wallet"])
async def test_onchain_links_use_configuration(
    app, event, monkeypatch, base_url, reference
):
    event.extra.onchain_enabled = True
    event.extra.onchain_wallet_id = reference
    monkeypatch.setattr(settings, "lnbits_baseurl", base_url)
    monkeypatch.setattr(views_api, "get_event", AsyncMock(return_value=event))
    monkeypatch.setattr(
        views_api, "get_wallet", AsyncMock(return_value=SimpleNamespace(inkey="key"))
    )
    charge = AsyncMock(return_value={"id": "charge"})
    save = AsyncMock()
    monkeypatch.setattr(views_api, "create_satspay_charge", charge)
    monkeypatch.setattr(views_api, "create_ticket", save)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="https://untrusted.example"
    ) as client:
        response = await client.post(
            f"/events/api/v1/tickets/{event.id}",
            json={
                "name": "Buyer",
                "email": "buyer@example.com",
                "payment_method": "onchain",
            },
        )
    if not base_url:
        assert response.status_code == 400
        assert "LNBITS_BASEURL" in response.json()["detail"]
        charge.assert_not_awaited()
        save.assert_not_awaited()
    else:
        assert response.status_code == 200
        data = charge.call_args.kwargs["data"]
        assert data["onchainwallet"] == reference
        assert data["zeroconf"] == event.extra.onchain_zeroconf
        assert data["fasttrack"] == event.extra.onchain_fasttrack
        assert data["completelink"].startswith(base_url + "events/ticket/")
        assert "untrusted.example" not in data["webhook"]
        assert "ticket_base_url" not in save.call_args.kwargs["extra"]


@pytest.mark.parametrize("reference", [None, "", "watch-id", "core:wallet_id-1"])
def test_onchain_reference_accepts_existing_and_core_values(reference):
    assert EventExtra(onchain_wallet_id=reference).onchain_wallet_id == reference


@pytest.mark.parametrize(
    "reference", ["core:", "other:id", "core:a:b", "core:a/b", "a?b", "a#b"]
)
def test_onchain_reference_rejects_malformed_values(reference):
    with pytest.raises(ValueError, match="Invalid onchain wallet reference"):
        EventExtra(onchain_wallet_id=reference)


@pytest.mark.asyncio
@pytest.mark.parametrize("reference", ["watch-id", "core:core-id"])
async def test_onchain_reference_persists(app, database, event, monkeypatch, reference):
    authorize(app, KeyType.admin)
    monkeypatch.setattr(
        views_api,
        "get_user",
        AsyncMock(return_value=SimpleNamespace(wallet_ids=["wallet", "core-id"])),
    )
    discover = AsyncMock(side_effect=RuntimeError("SatsPay unavailable"))
    monkeypatch.setattr(views_api, "fetch_core_onchain_wallets", discover)
    payload = CreateEvent(**event.dict()).dict()
    payload["extra"].update(onchain_enabled=True, onchain_wallet_id=reference)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post("/events/api/v1/events", json=payload)
        assert response.status_code == 200, response.text
        event_id = response.json()["id"]
        assert response.json()["extra"]["onchain_wallet_id"] == reference
        payload["name"] = "Updated"
        response = await client.put(f"/events/api/v1/events/{event_id}", json=payload)
        assert response.status_code == 200, response.text
        response = await client.get("/events/api/v1/events")
        assert response.json()[0]["extra"]["onchain_wallet_id"] == reference
    discover.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize(
    "reference, expected", [("core:wallet", 200), ("core:other", 403)]
)
async def test_core_configuration_requires_wallet_ownership(
    app, event, monkeypatch, method, reference, expected
):
    authorize(app, KeyType.admin)
    save = AsyncMock(return_value=event)
    monkeypatch.setattr(views_api, "create_event", save)
    monkeypatch.setattr(views_api, "update_event", save)
    monkeypatch.setattr(views_api, "get_event", AsyncMock(return_value=event))
    payload = CreateEvent(**event.dict()).dict()
    payload["extra"].update(onchain_enabled=True, onchain_wallet_id=reference)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        path = "/events/api/v1/events" + ("/event" if method == "PUT" else "")
        response = await client.request(method, path, json=payload)
    assert response.status_code == expected
    assert save.await_count == int(expected == 200)


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_source", ["watchonly", "watchonly-invalid", "core"])
async def test_onchain_sources_fail_independently(app, monkeypatch, failed_source):
    authorize(app, KeyType.admin)
    core = AsyncMock(return_value=[{"id": "core-id", "status": "ready"}])
    watch = AsyncMock(return_value=[{"id": "watch-id"}])
    config = AsyncMock(return_value={"network": "Mainnet"})
    if failed_source == "watchonly":
        config.side_effect = ValueError("private configuration")
    elif failed_source == "watchonly-invalid":
        config.return_value = {}
    else:
        core.side_effect = ValueError("private configuration")
    monkeypatch.setattr(views_api, "fetch_core_onchain_wallets", core)
    monkeypatch.setattr(views_api, "fetch_watchonly_config", config)
    monkeypatch.setattr(views_api, "fetch_watchonly_wallets", watch)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.get("/events/api/v1/events/onchain/status")
    assert response.status_code == 200
    data = response.json()
    assert "private configuration" not in response.text
    if failed_source.startswith("watchonly"):
        watch.assert_not_awaited()
        assert data["core_wallets"] == core.return_value
        assert data["message"]
        assert not data["wallets"]
    else:
        assert data["wallets"] == watch.return_value
        assert data["core_message"]
        assert not data["core_wallets"]
    core.assert_awaited_with("merchant-key")


@pytest.mark.asyncio
async def test_core_discovery_uses_merchant_key(monkeypatch):
    def respond(request):
        assert request.url.path == "/satspay/api/v1/onchain-wallets"
        assert request.headers["X-API-KEY"] == "merchant-key"
        return httpx.Response(200, json=[{"id": "core-id", "status": "ready"}])

    monkeypatch.setattr(
        services.httpx,
        "AsyncClient",
        lambda: AsyncClient(transport=httpx.MockTransport(respond)),
    )
    assert await services.fetch_core_onchain_wallets("merchant-key") == [
        {"id": "core-id", "status": "ready"}
    ]


@pytest.mark.asyncio
async def test_satspay_charge_preserves_actionable_errors(monkeypatch):
    def respond(request):
        assert request.headers["X-API-KEY"] == "merchant-key"
        assert json.loads(request.content)["onchainwallet"] == "core:core-id"
        return httpx.Response(
            400, json={"detail": "Onchain network mismatch. Testnet4 != Testnet"}
        )

    monkeypatch.setattr(
        services.httpx,
        "AsyncClient",
        lambda: AsyncClient(transport=httpx.MockTransport(respond)),
    )
    with pytest.raises(ValueError, match="Onchain network mismatch"):
        await services.create_satspay_charge(
            "merchant-key", {"onchainwallet": "core:core-id"}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_id, owner, expected",
    [(None, "other", 403), ("missing", None, 404), ("event", "other", 403)],
)
async def test_event_rejects_unowned_or_missing_event(
    app, event, monkeypatch, event_id, owner, expected
):
    authorize(app, KeyType.admin)
    event.wallet = owner or "wallet"
    monkeypatch.setattr(
        views_api, "get_event", AsyncMock(return_value=event if owner else None)
    )
    payload = CreateEvent(**event.dict()).dict()
    payload["extra"].update(onchain_enabled=True, onchain_wallet_id="core:core-id")
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.request(
            "PUT" if event_id else "POST",
            (
                f"/events/api/v1/events/{event_id}"
                if event_id
                else "/events/api/v1/events"
            ),
            json=payload,
        )
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target, original, expected",
    [
        ("second", "wallet", 200),
        ("wallet", "second", 200),
        ("other", "wallet", 403),
        ("wallet", "other", 403),
    ],
)
async def test_edit_event_uses_account_ownership(
    app, event, monkeypatch, target, original, expected
):
    authorize(app, KeyType.admin)
    monkeypatch.setattr(
        views_api,
        "get_user",
        AsyncMock(return_value=SimpleNamespace(wallet_ids=["wallet", "second"])),
    )
    event.wallet = original
    monkeypatch.setattr(views_api, "get_event", AsyncMock(return_value=event))
    save = AsyncMock(side_effect=lambda event: event)
    monkeypatch.setattr(views_api, "update_event", save)
    payload = CreateEvent(**event.dict()).dict()
    payload["wallet"] = target
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.put("/events/api/v1/events/event", json=payload)
    assert response.status_code == expected
    if expected == 200:
        assert response.json()["wallet"] == target
    else:
        save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("paid", [False, True])
async def test_satspay_webhook_verifies_charge_before_fulfilment(
    app, database, event, monkeypatch, method, paid
):
    await crud.create_event(CreateEvent(**event.dict()))
    monkeypatch.setattr(
        views_api,
        "get_wallet",
        AsyncMock(return_value=SimpleNamespace(inkey="merchant-key")),
    )
    ticket = await crud.create_ticket(
        "onchain-ticket",
        "wallet",
        event.id,
        "Buyer",
        "buyer@example.com",
        {"onchain": True, "satspay_charge_id": "charge"},
    )
    charge = AsyncMock(return_value={"paid": paid})
    monkeypatch.setattr(views_api, "get_satspay_charge", charge)
    monkeypatch.setattr(services, "get_event", AsyncMock(return_value=event))
    monkeypatch.setattr(services, "update_event", AsyncMock())
    notify = Mock()
    monkeypatch.setattr(views_api, "send_ticket_notification_in_background", notify)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            f"/events/api/v1/tickets/{ticket.id}/satspay-webhook",
            json={"paid": True},
        )
        assert response.status_code == 200
        # A repeated callback must not fulfil the ticket twice.
        await client.request(
            method, f"/events/api/v1/tickets/{ticket.id}/satspay-webhook"
        )
    saved = await crud.get_ticket(ticket.id)
    assert saved.paid == paid
    assert notify.call_count == int(paid)
    assert event.sold == int(paid)
    charge.assert_awaited_with("merchant-key", "charge")
