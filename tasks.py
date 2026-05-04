import asyncio

from lnbits.core.models import Payment
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import get_ticket
from .models import Ticket
from .services import set_ticket_paid

payment_listeners: dict[str, list[asyncio.Queue[Ticket]]] = {}


def register_payment_listener(payment_hash, queue: asyncio.Queue[Ticket]) -> None:
    if payment_hash not in payment_listeners:
        payment_listeners[payment_hash] = []
    payment_listeners[payment_hash].append(queue)


def deregister_payment_listener(payment_hash, queue: asyncio.Queue[Ticket]) -> None:
    if payment_hash in payment_listeners:
        payment_listeners[payment_hash].remove(queue)
        if not payment_listeners[payment_hash]:
            del payment_listeners[payment_hash]


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
    if payment_listeners.get(payment.payment_hash):
        for paid_ticket_queue in payment_listeners[payment.payment_hash]:
            paid_ticket_queue.put_nowait(ticket)
