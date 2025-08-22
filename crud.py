from datetime import datetime, timedelta, timezone

from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import CreateEvent, Event, Ticket

db = Database("ext_events")


async def create_ticket(
    payment_hash: str, wallet: str, event: str, name: str, email: str
) -> Ticket:
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        id=payment_hash,
        wallet=wallet,
        event=event,
        name=name,
        email=email,
        registered=False,
        paid=False,
        reg_timestamp=now,
        time=now,
    )
    await db.insert("events.ticket", ticket)
    return ticket


async def update_ticket(ticket: Ticket) -> Ticket:
    await db.update("events.ticket", ticket)
    return ticket


async def get_ticket(payment_hash: str) -> Ticket | None:
    return await db.fetchone(
        "SELECT * FROM events.ticket WHERE id = :id",
        {"id": payment_hash},
        Ticket,
    )


async def get_tickets(wallet_ids: str | list[str]) -> list[Ticket]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]
    q = ",".join([f"'{wallet_id}'" for wallet_id in wallet_ids])
    return await db.fetchall(
        f"SELECT * FROM events.ticket WHERE wallet IN ({q})",
        model=Ticket,
    )


async def delete_ticket(payment_hash: str) -> None:
    await db.execute("DELETE FROM events.ticket WHERE id = :id", {"id": payment_hash})


async def delete_event_tickets(event_id: str) -> None:
    await db.execute(
        "DELETE FROM events.ticket WHERE event = :event", {"event": event_id}
    )


async def purge_unpaid_tickets(event_id: str) -> None:
    time_diff = datetime.now() - timedelta(hours=24)
    await db.execute(
        f"""
        DELETE FROM events.ticket WHERE event = :event AND paid = false
        AND time < {db.timestamp_placeholder("time")}
        """,
        {"time": time_diff.timestamp(), "event": event_id},
    )


async def create_event(data: CreateEvent) -> Event:
    event_id = urlsafe_short_hash()
    event = Event(id=event_id, time=datetime.now(timezone.utc), **data.dict())
    await db.insert("events.events", event)
    return event


async def update_event(event: Event) -> Event:
    await db.update("events.events", event)
    return event


async def get_event(event_id: str) -> Event | None:
    return await db.fetchone(
        "SELECT * FROM events.events WHERE id = :id",
        {"id": event_id},
        Event,
    )


async def get_events(wallet_ids: str | list[str]) -> list[Event]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]
    q = ",".join([f"'{wallet_id}'" for wallet_id in wallet_ids])
    return await db.fetchall(
        f"SELECT * FROM events.events WHERE wallet IN ({q})",
        model=Event,
    )


async def delete_event(event_id: str) -> None:
    await db.execute("DELETE FROM events.events WHERE id = :id", {"id": event_id})


async def get_event_tickets(event_id: str) -> list[Ticket]:
    return await db.fetchall(
        "SELECT * FROM events.ticket WHERE event = :event",
        {"event": event_id},
        Ticket,
    )
