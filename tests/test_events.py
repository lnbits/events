import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from lnbits.core.models import KeyType
from lnbits.db import Database
from lnbits.settings import settings

from .. import crud, migrations, views_api
from ..models import CreateEvent, Event, EventExtra, PromoCode


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


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(views_api.events_api_router, prefix="/events")
    app.include_router(views_api.tickets_api_router, prefix="/events")
    return app


def authorize(app, key_type):
    wallet = SimpleNamespace(id="wallet", user="user")
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
