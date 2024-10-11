from datetime import datetime, timezone
from http import HTTPStatus
from typing import Optional

from fastapi import APIRouter, Depends, Query
from lnbits.core.crud import get_standalone_payment, get_user
from lnbits.core.models import WalletTypeInfo
from lnbits.core.services import create_invoice
from lnbits.decorators import (
    require_admin_key,
    require_invoice_key,
)
from lnbits.utils.exchange_rates import (
    fiat_amount_as_satoshis,
    get_fiat_rate_satoshis,
)
from starlette.exceptions import HTTPException

from .crud import (
    create_event,
    create_ticket,
    delete_event,
    delete_event_tickets,
    delete_ticket,
    get_event,
    get_event_tickets,
    get_events,
    get_ticket,
    get_tickets,
    purge_unpaid_tickets,
    update_event,
    update_ticket,
)
from .models import CreateEvent, CreateTicket, Ticket
from .services import set_ticket_paid

events_api_router = APIRouter()


@events_api_router.get("/api/v1/events")
async def api_events(
    all_wallets: bool = Query(False),
    wallet: WalletTypeInfo = Depends(require_invoice_key),
):
    wallet_ids = [wallet.wallet.id]

    if all_wallets:
        user = await get_user(wallet.wallet.user)
        wallet_ids = user.wallet_ids if user else []

    return [event.dict() for event in await get_events(wallet_ids)]


@events_api_router.post("/api/v1/events")
@events_api_router.put("/api/v1/events/{event_id}")
async def api_event_create(
    data: CreateEvent,
    wallet: WalletTypeInfo = Depends(require_admin_key),
    event_id: Optional[str] = None,
):
    if event_id:
        event = await get_event(event_id)
        if not event:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
            )

        if event.wallet != wallet.wallet.id:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN, detail="Not your event."
            )
        for k, v in data.dict().items():
            setattr(event, k, v)
        event = await update_event(event)
    else:
        event = await create_event(data)

    return event.dict()


@events_api_router.delete("/api/v1/events/{event_id}")
async def api_form_delete(
    event_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
):
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )

    if event.wallet != wallet.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your event.")

    await delete_event(event_id)
    await delete_event_tickets(event_id)
    return "", HTTPStatus.NO_CONTENT


#########Tickets##########


@events_api_router.get("/api/v1/tickets")
async def api_tickets(
    all_wallets: bool = Query(False),
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Ticket]:
    wallet_ids = [wallet.wallet.id]

    if all_wallets:
        user = await get_user(wallet.wallet.user)
        wallet_ids = user.wallet_ids if user else []

    return await get_tickets(wallet_ids)


@events_api_router.post("/api/v1/tickets/{event_id}")
async def api_ticket_create(event_id: str, data: CreateTicket):
    name = data.name
    email = data.email
    return await api_ticket_make_ticket(event_id, name, email)


@events_api_router.get("/api/v1/tickets/{event_id}/{name}/{email}")
async def api_ticket_make_ticket(event_id, name, email):
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )

    price = event.price_per_ticket
    extra = {"tag": "events", "name": name, "email": email}

    if event.currency != "sat":
        price = await fiat_amount_as_satoshis(event.price_per_ticket, event.currency)

        extra["fiat"] = True
        extra["currency"] = event.currency
        extra["fiatAmount"] = event.price_per_ticket
        extra["rate"] = await get_fiat_rate_satoshis(event.currency)

    try:
        payment_hash, payment_request = await create_invoice(
            wallet_id=event.wallet,
            amount=price,  # type: ignore
            memo=f"{event_id}",
            extra=extra,
        )
        await create_ticket(
            payment_hash=payment_hash,
            wallet=event.wallet,
            event=event.id,
            name=name,
            email=email,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    return {"payment_hash": payment_hash, "payment_request": payment_request}


@events_api_router.post("/api/v1/tickets/{event_id}/{payment_hash}")
async def api_ticket_send_ticket(event_id, payment_hash):
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Event could not be fetched.",
        )

    ticket = await get_ticket(payment_hash)
    if not ticket:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Ticket could not be fetched.",
        )
    payment = await get_standalone_payment(payment_hash, incoming=True)
    assert payment
    price = (
        event.price_per_ticket * 1000
        if event.currency == "sat"
        else await fiat_amount_as_satoshis(event.price_per_ticket, event.currency)
        * 1000
    )
    # check if price is equal to payment.amount
    lower_bound = price * 0.99  # 1% decrease

    if not payment.pending and abs(payment.amount) >= lower_bound:  # allow 1% error
        await set_ticket_paid(ticket)
        return {"paid": True, "ticket_id": ticket.id}

    return {"paid": False}


@events_api_router.delete("/api/v1/tickets/{ticket_id}")
async def api_ticket_delete(
    ticket_id: str, wallet: WalletTypeInfo = Depends(require_invoice_key)
):
    ticket = await get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Ticket does not exist."
        )

    if ticket.wallet != wallet.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your ticket.")

    await delete_ticket(ticket_id)


# TODO: DELETE, updates db! @tal
@events_api_router.get("/api/v1/purge/{event_id}")
async def api_event_purge_tickets(event_id: str):
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )
    return await purge_unpaid_tickets(event_id)


@events_api_router.get("/api/v1/eventtickets/{event_id}")
async def api_event_tickets(event_id: str) -> list[Ticket]:
    return await get_event_tickets(event_id)


# TODO: PUT, updates db! @tal
@events_api_router.get("/api/v1/register/ticket/{ticket_id}")
async def api_event_register_ticket(ticket_id) -> list[Ticket]:
    ticket = await get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Ticket does not exist."
        )

    if not ticket.paid:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Ticket not paid for."
        )

    if ticket.registered is True:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Ticket already registered"
        )

    ticket.registered = True
    ticket.reg_timestamp = datetime.now(timezone.utc)
    await update_ticket(ticket)
    return await get_event_tickets(ticket.event)
