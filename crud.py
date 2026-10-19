from datetime import datetime, timedelta, timezone
from typing import cast

from lnbits.db import Database, Filters, Page
from lnbits.helpers import urlsafe_short_hash
from sqlalchemy.exc import IntegrityError  # type: ignore[import-untyped]

from .models import (
    CreateEvent,
    Event,
    Ticket,
    TicketExtra,
    TicketFilters,
    TicketRefund,
    sync_event_ticket_waves,
)

db = Database("ext_events")


async def create_ticket(
    payment_hash: str, wallet: str, event: str, name: str, email: str, extra: dict
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
        extra=TicketExtra(**extra) if extra else TicketExtra(),
    )
    await db.insert("events.ticket", ticket)
    return ticket


async def update_ticket(ticket: Ticket) -> Ticket:
    await db.update("events.ticket", ticket)
    return ticket


async def register_ticket(ticket: Ticket) -> bool:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        f"""
        UPDATE events.ticket SET registered = true,
            reg_timestamp = {db.timestamp_placeholder("reg_timestamp")}
        WHERE id = :id AND paid = true AND registered = false
        """,
        {"id": ticket.id, "reg_timestamp": now.timestamp()},
    )
    if result.rowcount != 1:
        return False
    ticket.registered = True
    ticket.reg_timestamp = now
    return True


async def get_ticket_refund(ticket_id: str) -> TicketRefund | None:
    return await db.fetchone(
        "SELECT * FROM events.refunds WHERE id = :id", {"id": ticket_id}, TicketRefund
    )


async def create_ticket_refund(refund: TicketRefund) -> TicketRefund:
    try:
        await db.insert("events.refunds", refund)
    except IntegrityError:
        existing = await get_ticket_refund(refund.id)
        if not existing:
            raise ValueError("Refund invoice is already assigned.") from None
        return existing
    return refund


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


async def get_tickets_paginated(
    wallet_ids: str | list[str], filters: Filters[TicketFilters] | None = None
) -> Page[Ticket]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]

    wallet_where = []
    values = {}
    for idx, wallet_id in enumerate(wallet_ids):
        key = f"wallet_id_{idx}"
        wallet_where.append(f":{key}")
        values[key] = wallet_id

    where = [f"wallet IN ({', '.join(wallet_where)})", "paid = true"]

    return await db.fetch_page(
        "SELECT * FROM events.ticket",
        where=where,
        values=values,
        filters=filters,
        model=Ticket,
        table_name="events.ticket",
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
    event = cast(Event, sync_event_ticket_waves(event))
    await db.insert("events.events", event)
    return event


async def update_event(event: Event) -> Event:
    event = cast(Event, sync_event_ticket_waves(event))
    await db.update("events.events", event)
    return event


async def get_event(event_id: str) -> Event | None:
    event = await db.fetchone(
        "SELECT * FROM events.events WHERE id = :id",
        {"id": event_id},
        Event,
    )
    return cast(Event, sync_event_ticket_waves(event)) if event else None


async def get_events(wallet_ids: str | list[str]) -> list[Event]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]
    q = ",".join([f"'{wallet_id}'" for wallet_id in wallet_ids])
    events = await db.fetchall(
        f"SELECT * FROM events.events WHERE wallet IN ({q})",
        model=Event,
    )
    return [cast(Event, sync_event_ticket_waves(event)) for event in events]


async def get_closed_events() -> list[Event]:
    return await db.fetchall(
        """
        SELECT * FROM events.events WHERE close_processed = false
        AND (canceled = true OR closing_date < :today)
        """,
        {"today": datetime.now(timezone.utc).date().isoformat()},
        Event,
    )


async def mark_event_closed(event: Event) -> None:
    await db.execute(
        """
        UPDATE events.events SET close_processed = true
        WHERE id = :id AND sold = :sold AND canceled = :canceled
        AND closing_date = :closing_date
        """,
        {
            "id": event.id,
            "sold": event.sold,
            "canceled": event.canceled,
            "closing_date": event.closing_date,
        },
    )


async def delete_event(event_id: str) -> None:
    await db.execute("DELETE FROM events.events WHERE id = :id", {"id": event_id})


async def get_event_tickets(event_id: str) -> list[Ticket]:
    return await db.fetchall(
        "SELECT * FROM events.ticket WHERE event = :event",
        {"event": event_id},
        Ticket,
    )
