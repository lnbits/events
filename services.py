from lnurl import execute
from loguru import logger

from .crud import (
    get_event,
    get_event_tickets,
    purge_unpaid_tickets,
    update_event,
    update_ticket,
)
from .models import Ticket


async def set_ticket_paid(ticket: Ticket) -> Ticket:
    if ticket.paid:
        return ticket

    ticket.paid = True
    await update_ticket(ticket)

    event = await get_event(ticket.event)
    assert event, "Couldn't get event from ticket being paid"
    event.sold += 1
    event.amount_tickets -= 1
    await update_event(event)

    return ticket


async def refund_tickets(event_id: str):
    """
    Refund tickets for an event that has not met the minimum ticket requirement.
    This function should be called when the event is closed and the minimum ticket
    condition is not met.
    """
    event = await get_event(event_id)
    if not event:
        return

    await purge_unpaid_tickets(event_id)
    tickets = await get_event_tickets(event_id)

    if not tickets:
        return

    for ticket in tickets:
        if ticket.extra.refunded:
            continue
        if ticket.paid and ticket.extra.refund_address and ticket.extra.sats_paid:
            try:
                res = await execute(
                    ticket.extra.refund_address, str(ticket.extra.sats_paid)
                )
                if res:
                    ticket.extra.refunded = True
                    await update_ticket(ticket)
            except Exception as e:
                logger.error(f"Error refunding ticket {ticket.id}: {e}")
