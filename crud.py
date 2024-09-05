from datetime import datetime, timedelta
from typing import List, Optional, Union

from lnbits.db import Database
from lnbits.helpers import insert_query, update_query, urlsafe_short_hash

from .models import CreateEvent, Event, Ticket

db = Database("ext_events")


async def create_ticket(
    payment_hash: str, wallet: str, event: str, name: str, email: str
) -> Ticket:
    await db.execute(
        """
        INSERT INTO events.ticket (id, wallet, event, name, email, registered, paid)
        VALUES (:payment_hash, :wallet, :event, :name, :email, :registered, :paid)
        """,
        {
            "payment_hash": payment_hash,
            "wallet": wallet,
            "event": event,
            "name": name,
            "email": email,
            "registered": False,
            "paid": False,
        },
    )

    ticket = await get_ticket(payment_hash)
    assert ticket, "Newly created ticket couldn't be retrieved"
    return ticket


async def set_ticket_paid(payment_hash: str) -> Ticket:
    ticket = await get_ticket(payment_hash)
    assert ticket, "Ticket couldn't be retrieved"
    if ticket.paid:
        return ticket

    await db.execute(
        "UPDATE events.ticket SET paid = :paid WHERE id = :id",
        {"paid": True, "id": payment_hash},
    )

    await update_event_sold(ticket.event)

    return ticket


async def update_event_sold(event_id: str):
    event = await get_event(event_id)
    assert event, "Couldn't get event from ticket being paid"
    sold = event.sold + 1
    amount_tickets = event.amount_tickets - 1
    await db.execute(
        """
        UPDATE events.events
        SET sold = :sold, amount_tickets = :amount WHERE id = :id
        """,
        {"sold": sold, "amount": amount_tickets, "id": event_id},
    )

    return


async def get_ticket(payment_hash: str) -> Optional[Ticket]:
    row = await db.fetchone(
        "SELECT * FROM events.ticket WHERE id = :id",
        {"id": payment_hash},
    )
    return Ticket(**row) if row else None


async def get_tickets(wallet_ids: Union[str, List[str]]) -> List[Ticket]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]
    q = ",".join([f"'{wallet_id}'" for wallet_id in wallet_ids])
    rows = await db.fetchall(f"SELECT * FROM events.ticket WHERE wallet IN ({q})")
    return [Ticket(**row) for row in rows]


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
    event = Event(id=event_id, time=int(datetime.now().timestamp()), **data.dict())
    await db.execute(
        insert_query("events.events", event),
        event.dict(),
    )
    return event


async def update_event(event: Event) -> Event:
    await db.execute(
        update_query("events.events", event),
        event.dict(),
    )
    return event


async def get_event(event_id: str) -> Optional[Event]:
    row = await db.fetchone(
        "SELECT * FROM events.events WHERE id = :id", {"id": event_id}
    )
    return Event(**row) if row else None


async def get_events(wallet_ids: Union[str, List[str]]) -> List[Event]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]

    q = ",".join([f"'{wallet_id}'" for wallet_id in wallet_ids])
    rows = await db.fetchall(f"SELECT * FROM events.events WHERE wallet IN ({q})")
    return [Event(**row) for row in rows]


async def delete_event(event_id: str) -> None:
    await db.execute("DELETE FROM events.events WHERE id = :id", {"id": event_id})


async def get_event_tickets(event_id: str, wallet_id: str) -> List[Ticket]:
    rows = await db.fetchall(
        "SELECT * FROM events.ticket WHERE wallet = :wallet AND event = :event",
        {"wallet": wallet_id, "event": event_id},
    )
    return [Ticket(**row) for row in rows]


async def reg_ticket(ticket_id: str) -> List[Ticket]:
    await db.execute(
        f"""
        UPDATE events.ticket SET registered = :registered,
        reg_timestamp = {db.timestamp_placeholder('now')} WHERE id = :id
        """,
        {"registered": True, "now": datetime.now().timestamp(), "id": ticket_id},
    )
    ticket = await db.fetchone(
        "SELECT * FROM events.ticket WHERE id = :id", {"id": ticket_id}
    )
    rows = await db.fetchall(
        "SELECT * FROM events.ticket WHERE event = :event", {"event": ticket["event"]}
    )
    return [Ticket(**row) for row in rows]
