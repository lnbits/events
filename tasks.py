import asyncio

from .models import Ticket

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
