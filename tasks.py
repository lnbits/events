import asyncio

from lnbits.core.models import Payment
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import get_ticket
from .services import set_ticket_paid


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, "ext_events")

    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)


async def on_invoice_paid(payment: Payment) -> None:
    if not payment.extra or "events" != payment.extra.get("tag"):
        return

    # Check if ticket has either name/email or user_id
    has_name_email = payment.extra.get("name") and payment.extra.get("email")
    has_user_id = payment.extra.get("user_id")
    
    if not has_name_email and not has_user_id:
        logger.warning(f"Ticket {payment.payment_hash} missing name/email or user_id.")
        return

    ticket = await get_ticket(payment.payment_hash)
    if not ticket:
        logger.warning(f"Ticket for payment {payment.payment_hash} not found.")
        return

    await set_ticket_paid(ticket)
