import asyncio

from lnbits.core.models import Payment
from lnbits.tasks import register_invoice_listener

from .crud import set_ticket_paid


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, "ext_events")

    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)


async def on_invoice_paid(payment: Payment) -> None:
    # (avoid loops)
    if (
        payment.extra
        and "events" == payment.extra.get("tag")
        and payment.extra.get("name")
        and payment.extra.get("email")
    ):
        await set_ticket_paid(payment.payment_hash)
    return
