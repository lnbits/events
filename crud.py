import json
from datetime import datetime, timedelta, timezone

from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import CreateEvent, Event, Ticket, TicketExtra

db = Database("ext_events")


def _parse_ticket_row(row) -> dict:
    """Normalize a ticket row before constructing a Ticket model.

    - Empty-string sentinels in name/email (used because the DB columns are
      NOT NULL but the Pydantic field is Optional when user_id is set) are
      converted back to None.
    - The `extra` JSON column may come back as a string when the row is
      fetched without a model= argument; parse it so Pydantic can build
      TicketExtra from a dict.
    """
    ticket_data = dict(row)

    if ticket_data.get("name") == "":
        ticket_data["name"] = None
    if ticket_data.get("email") == "":
        ticket_data["email"] = None

    extra = ticket_data.get("extra")
    if isinstance(extra, str):
        ticket_data["extra"] = json.loads(extra) if extra else {}

    return ticket_data


async def create_ticket(
    payment_hash: str,
    wallet: str,
    event: str,
    name: str | None = None,
    email: str | None = None,
    user_id: str | None = None,
    extra: dict | None = None,
) -> Ticket:
    now = datetime.now(timezone.utc)

    # name/email columns are NOT NULL in the schema, so we store "" when only
    # user_id is supplied. _parse_ticket_row reverses this on read.
    if user_id:
        db_name = ""
        db_email = ""
    else:
        db_name = name or ""
        db_email = email or ""

    db_ticket = Ticket(
        id=payment_hash,
        wallet=wallet,
        event=event,
        name=db_name,
        email=db_email,
        user_id=user_id,
        registered=False,
        paid=False,
        reg_timestamp=now,
        time=now,
        extra=TicketExtra(**extra) if extra else TicketExtra(),
    )
    await db.insert("events.ticket", db_ticket)

    return Ticket(
        id=payment_hash,
        wallet=wallet,
        event=event,
        name=name,
        email=email,
        user_id=user_id,
        registered=False,
        paid=False,
        reg_timestamp=now,
        time=now,
        extra=TicketExtra(**extra) if extra else TicketExtra(),
    )


async def update_ticket(ticket: Ticket) -> Ticket:
    ticket_dict = ticket.dict()
    if ticket_dict.get("name") is None:
        ticket_dict["name"] = ""
    if ticket_dict.get("email") is None:
        ticket_dict["email"] = ""
    await db.update("events.ticket", Ticket(**ticket_dict))
    return ticket


async def get_ticket(payment_hash: str) -> Ticket | None:
    row = await db.fetchone(
        "SELECT * FROM events.ticket WHERE id = :id",
        {"id": payment_hash},
    )
    if not row:
        return None
    return Ticket(**_parse_ticket_row(row))


async def get_tickets(wallet_ids: str | list[str]) -> list[Ticket]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]
    q = ",".join([f"'{wallet_id}'" for wallet_id in wallet_ids])
    rows = await db.fetchall(f"SELECT * FROM events.ticket WHERE wallet IN ({q})")
    return [Ticket(**_parse_ticket_row(row)) for row in rows]


async def get_tickets_by_user_id(user_id: str) -> list[Ticket]:
    """All tickets owned by the given LNbits user_id."""
    rows = await db.fetchall(
        "SELECT * FROM events.ticket WHERE user_id = :user_id ORDER BY time DESC",
        {"user_id": user_id},
    )
    return [Ticket(**_parse_ticket_row(row)) for row in rows]


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
    rows = await db.fetchall(
        "SELECT * FROM events.ticket WHERE event = :event",
        {"event": event_id},
    )
    return [Ticket(**_parse_ticket_row(row)) for row in rows]
