from datetime import datetime, timedelta, timezone

from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import CreateEvent, Event, Ticket

db = Database("ext_events")


async def create_ticket(
    payment_hash: str, 
    wallet: str, 
    event: str, 
    name: Optional[str] = None, 
    email: Optional[str] = None,
    user_id: Optional[str] = None
) -> Ticket:
    now = datetime.now(timezone.utc)
    
    # Handle database constraints: if user_id is provided, use empty strings for name/email
    if user_id:
        db_name = ""
        db_email = ""
    else:
        db_name = name or ""
        db_email = email or ""
    
    ticket = Ticket(
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
    )
    
    # Create a dict for database insertion with proper handling of constraints
    ticket_dict = ticket.dict()
    ticket_dict["name"] = db_name
    ticket_dict["email"] = db_email
    
    await db.execute(
        """
        INSERT INTO events.ticket (id, wallet, event, name, email, user_id, registered, paid, time, reg_timestamp)
        VALUES (:id, :wallet, :event, :name, :email, :user_id, :registered, :paid, :time, :reg_timestamp)
        """,
        ticket_dict
    )
    return ticket


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


async def get_ticket(payment_hash: str) -> Ticket | None:
    return await db.fetchone(
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
