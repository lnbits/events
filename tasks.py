import asyncio

from lnbits.core.models import Payment
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import get_ticket
from .models import Ticket
from .services import set_ticket_paid

paid_invoice_queue: asyncio.Queue[Ticket] = asyncio.Queue()


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, "ext_events")

    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)


async def on_invoice_paid(payment: Payment) -> None:
    if not payment.extra or "events" != payment.extra.get("tag"):
        return

    ticket = await get_ticket(payment.payment_hash)
    if not ticket:
        logger.warning(f"Ticket for payment {payment.payment_hash} not found.")
        return

    ticket = await set_ticket_paid(ticket)
    paid_invoice_queue.put_nowait(ticket)
