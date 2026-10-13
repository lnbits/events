# In-memory CRUD stub backing the real events/services.py during tests.
from datetime import datetime, timezone

from events.models import Ticket, TicketExtra

_STORE = {"tickets": {}, "ticket_types": {}, "events": {}, "baskets": {}}


def reset():
    """Empty the in-memory store (used between tests)."""
    for collection in _STORE.values():
        collection.clear()


def _now():
    return datetime.now(timezone.utc)


# --- tickets ---
async def create_ticket(payment_hash, wallet, event, name, email, extra,
                        ticket_type_id=None, basket_id=None):
    t = Ticket(id=payment_hash, wallet=wallet, event=event, name=name, email=email,
               registered=False, paid=False, reg_timestamp=_now(), time=_now(),
               ticket_type_id=ticket_type_id, basket_id=basket_id,
               extra=TicketExtra(**extra) if extra else TicketExtra())
    _STORE["tickets"][t.id] = t
    return t


async def update_ticket(ticket):
    _STORE["tickets"][ticket.id] = ticket
    return ticket


async def get_ticket(payment_hash):
    return _STORE["tickets"].get(payment_hash)


async def get_tickets(wallet_ids):
    ids = wallet_ids if isinstance(wallet_ids, list) else [wallet_ids]
    return [t for t in _STORE["tickets"].values() if t.wallet in ids]


async def get_event_tickets(event_id):
    return [t for t in _STORE["tickets"].values() if t.event == event_id]


async def get_basket_tickets(basket_id):
    return [t for t in _STORE["tickets"].values() if t.basket_id == basket_id]


async def delete_ticket(ticket_id):
    _STORE["tickets"].pop(ticket_id, None)


async def delete_event_tickets(event_id):
    for k in [k for k in _STORE["tickets"] if _STORE["tickets"][k].event == event_id]:
        _STORE["tickets"].pop(k, None)


async def purge_unpaid_tickets(event_id):
    for k in [k for k in _STORE["tickets"]
              if _STORE["tickets"][k].event == event_id and not _STORE["tickets"][k].paid]:
        _STORE["tickets"].pop(k, None)


# --- ticket types ---
async def get_ticket_types(event_id):
    return [tt for tt in _STORE["ticket_types"].values() if tt.event_id == event_id]


async def get_ticket_type(tt_id):
    return _STORE["ticket_types"].get(tt_id)


async def get_all_ticket_types():
    return list(_STORE["ticket_types"].values())


async def count_tickets_by_type(ticket_type_id):
    return sum(1 for t in _STORE["tickets"].values()
               if t.ticket_type_id == ticket_type_id)


async def create_ticket_type(ticket_type):
    _STORE["ticket_types"][ticket_type.id] = ticket_type
    return ticket_type


async def update_ticket_type(ticket_type):
    _STORE["ticket_types"][ticket_type.id] = ticket_type
    return ticket_type


async def delete_ticket_type(tt_id):
    _STORE["ticket_types"].pop(tt_id, None)


# --- events ---
async def create_event(event):
    _STORE["events"][event.id] = event
    return event


async def update_event(event):
    _STORE["events"][event.id] = event
    return event


async def get_event(event_id):
    return _STORE["events"].get(event_id)


async def get_events(*a, **k):
    return list(_STORE["events"].values())


# --- baskets ---
async def create_basket(basket):
    _STORE["baskets"][basket.id] = basket
    return basket


async def update_basket(basket):
    _STORE["baskets"][basket.id] = basket
    return basket


async def get_basket(basket_id):
    return _STORE["baskets"].get(basket_id)


async def get_event_baskets(event_id):
    return [b for b in _STORE["baskets"].values() if b.event_id == event_id]
