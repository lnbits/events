from datetime import datetime, timedelta
from typing import List, Optional, Union

from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import CreateEvent, Event, Ticket

db = Database("ext_events")


async def create_ticket(
    payment_hash: str, wallet: str, event: str, name: str, email: str
) -> Ticket:
    await db.execute(
        """
        INSERT INTO events.ticket (id, wallet, event, name, email, registered, paid)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (payment_hash, wallet, event, name, email, False, False),
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
        """
        UPDATE events.ticket
        SET paid = ?
        WHERE id = ?
        """,
        (True, ticket.id),
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
        SET sold = ?, amount_tickets = ?
        WHERE id = ?
        """,
        (sold, amount_tickets, event_id),
    )

    return


async def get_ticket(payment_hash: str) -> Optional[Ticket]:
    row = await db.fetchone("SELECT * FROM events.ticket WHERE id = ?", (payment_hash,))
    return Ticket(**row) if row else None


async def get_tickets(wallet_ids: Union[str, List[str]]) -> List[Ticket]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]

    q = ",".join(["?"] * len(wallet_ids))
    rows = await db.fetchall(
        f"SELECT * FROM events.ticket WHERE wallet IN ({q})", (*wallet_ids,)
    )
    return [Ticket(**row) for row in rows]


async def delete_ticket(payment_hash: str) -> None:
    await db.execute("DELETE FROM events.ticket WHERE id = ?", (payment_hash,))


async def delete_event_tickets(event_id: str) -> None:
    await db.execute("DELETE FROM events.ticket WHERE event = ?", (event_id,))


async def purge_unpaid_tickets(event_id: str) -> None:
    time_diff = datetime.now() - timedelta(hours=24)
    await db.execute(
        f"""
        DELETE FROM events.ticket WHERE event = ? AND paid = false
        AND time < {db.timestamp_placeholder}
        """,
        (
            event_id,
            time_diff.timestamp(),
        ),
    )


async def create_event(data: CreateEvent) -> Event:
    event_id = urlsafe_short_hash()
    await db.execute(
        """
        INSERT INTO events.events (
            id, wallet, name, info, banner, closing_date, event_start_date,
            event_end_date, currency, amount_tickets, price_per_ticket, sold
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            data.wallet,
            data.name,
            data.info,
            data.banner,
            data.closing_date,
            data.event_start_date,
            data.event_end_date,
            data.currency,
            data.amount_tickets,
            data.price_per_ticket,
            0,
        ),
    )

    event = await get_event(event_id)
    assert event, "Newly created event couldn't be retrieved"
    return event


async def update_event(event_id: str, **kwargs) -> Event:
    q = ", ".join([f"{field[0]} = ?" for field in kwargs.items()])
    await db.execute(
        f"UPDATE events.events SET {q} WHERE id = ?", (*kwargs.values(), event_id)
    )
    event = await get_event(event_id)
    assert event, "Newly updated event couldn't be retrieved"
    return event


async def get_event(event_id: str) -> Optional[Event]:
    row = await db.fetchone("SELECT * FROM events.events WHERE id = ?", (event_id,))
    return Event(**row) if row else None


async def get_events(wallet_ids: Union[str, List[str]]) -> List[Event]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]

    q = ",".join(["?"] * len(wallet_ids))
    rows = await db.fetchall(
        f"SELECT * FROM events.events WHERE wallet IN ({q})", (*wallet_ids,)
    )

    return [Event(**row) for row in rows]


async def delete_event(event_id: str) -> None:
    await db.execute("DELETE FROM events.events WHERE id = ?", (event_id,))


# EVENTTICKETS


async def get_event_tickets(event_id: str, wallet_id: str) -> List[Ticket]:
    rows = await db.fetchall(
        "SELECT * FROM events.ticket WHERE wallet = ? AND event = ?",
        (wallet_id, event_id),
    )
    return [Ticket(**row) for row in rows]


async def reg_ticket(ticket_id: str) -> List[Ticket]:
    await db.execute(
        f"""
        UPDATE events.ticket SET registered = ?,
        reg_timestamp = {db.timestamp_now} WHERE id = ?
        """,
        (True, ticket_id),
    )
    ticket = await db.fetchone("SELECT * FROM events.ticket WHERE id = ?", (ticket_id,))
    rows = await db.fetchall(
        "SELECT * FROM events.ticket WHERE event = ?", (ticket[1],)
    )
    return [Ticket(**row) for row in rows]
