from datetime import datetime, timedelta, timezone
from typing import Optional

from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import CreateEvent, Event, Ticket, TicketExtra

db = Database("ext_events")


async def create_ticket(
    payment_hash: str,
    wallet: str,
    event: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    user_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> Ticket:
    now = datetime.now(timezone.utc)

    # TODO: Check if this empty string workaround is still needed.
    # This converts None to empty strings for database storage because:
    # 1. Database may have NOT NULL constraints on name/email columns
    # 2. When user_id is provided, name/email are not used (mutually exclusive)
    # 3. The get_ticket() functions convert empty strings back to None when reading
    # Consider using nullable columns instead of this empty string pattern.
    if user_id:
        db_name = ""
        db_email = ""
    else:
        db_name = name or ""
        db_email = email or ""

    # Create ticket with database-compatible values for insertion
    # Using db.insert() ensures proper serialization of the extra field (TicketExtra)
    # across all database backends (SQLite, PostgreSQL, CockroachDB)
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

    # Return ticket with original name/email values (not empty strings)
    # This maintains consistency with how get_ticket() converts empty strings back to None
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
    # Create a new Ticket object with corrected values for database constraints
    ticket_dict = ticket.dict()

    # Convert None values to empty strings for database constraints
    if ticket_dict.get("name") is None:
        ticket_dict["name"] = ""
    if ticket_dict.get("email") is None:
        ticket_dict["email"] = ""

    # Create a new Ticket object with the corrected values
    corrected_ticket = Ticket(**ticket_dict)

    await db.update("events.ticket", corrected_ticket)
    return ticket


async def get_ticket(payment_hash: str) -> Optional[Ticket]:
    row = await db.fetchone(
        "SELECT * FROM events.ticket WHERE id = :id",
        {"id": payment_hash},
    )
    if not row:
        return None

    # Convert empty strings back to None for the model
    ticket_data = dict(row)
    if ticket_data.get("name") == "":
        ticket_data["name"] = None
    if ticket_data.get("email") == "":
        ticket_data["email"] = None

    return Ticket(**ticket_data)


async def get_tickets(wallet_ids: str | list[str]) -> list[Ticket]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]
    q = ",".join([f"'{wallet_id}'" for wallet_id in wallet_ids])
    rows = await db.fetchall(f"SELECT * FROM events.ticket WHERE wallet IN ({q})")

    tickets = []
    for row in rows:
        # Convert empty strings back to None for the model
        ticket_data = dict(row)
        if ticket_data.get("name") == "":
            ticket_data["name"] = None
        if ticket_data.get("email") == "":
            ticket_data["email"] = None
        tickets.append(Ticket(**ticket_data))

    return tickets


async def get_tickets_by_user_id(user_id: str) -> list[Ticket]:
    """Get all tickets for a specific user by their user_id"""
    rows = await db.fetchall(
        "SELECT * FROM events.ticket WHERE user_id = :user_id ORDER BY time DESC",
        {"user_id": user_id}
    )

    tickets = []
    for row in rows:
        # Convert empty strings back to None for the model
        ticket_data = dict(row)
        if ticket_data.get("name") == "":
            ticket_data["name"] = None
        if ticket_data.get("email") == "":
            ticket_data["email"] = None
        tickets.append(Ticket(**ticket_data))

    return tickets


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


async def get_all_events() -> list[Event]:
    """Get all events from the database without wallet filtering."""
    return await db.fetchall(
        "SELECT * FROM events.events ORDER BY time DESC",
        model=Event,
    )


async def delete_event(event_id: str) -> None:
    await db.execute("DELETE FROM events.events WHERE id = :id", {"id": event_id})


async def get_event_tickets(event_id: str) -> list[Ticket]:
    rows = await db.fetchall(
        "SELECT * FROM events.ticket WHERE event = :event",
        {"event": event_id},
    )

    tickets = []
    for row in rows:
        # Convert empty strings back to None for the model
        ticket_data = dict(row)
        if ticket_data.get("name") == "":
            ticket_data["name"] = None
        if ticket_data.get("email") == "":
            ticket_data["email"] = None
        tickets.append(Ticket(**ticket_data))

    return tickets
