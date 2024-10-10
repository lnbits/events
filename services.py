from .crud import get_event, update_event, update_ticket
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
