import asyncio
from typing import Any
from datetime import datetime, timezone
from http import HTTPStatus

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from lnbits.core.crud import get_user
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
from .models import (
    CreateEvent,
    CreateTicket,
    Event,
    PublicEvent,
    PublicTicket,
    Ticket,
    TicketPaymentRequest,
)
from .services import refund_tickets
from .tasks import deregister_payment_listener, register_payment_listener

events_api_router = APIRouter(prefix="/api/v1/events")
tickets_api_router = APIRouter(prefix="/api/v1/tickets")


@events_api_router.get("")
async def api_events(
    all_wallets: bool = Query(False),
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Event]:
    wallet_ids = [wallet.wallet.id]

    if all_wallets:
        user = await get_user(wallet.wallet.user)
        wallet_ids = user.wallet_ids if user else []

    return await get_events(wallet_ids)


@events_api_router.get("/{event_id}", response_model=PublicEvent)
async def api_get_event(event_id: str) -> Event:
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )
    await purge_unpaid_tickets(event_id)

    is_window_open = datetime.now(timezone.utc) < datetime.strptime(
        event.closing_date, "%Y-%m-%d"
    ).replace(tzinfo=timezone.utc)
    is_min_tickets_met = (
        event.sold >= event.extra.min_tickets if event.extra.conditional else True
    )
    if event.amount_tickets < 1:
        raise HTTPException(status_code=HTTPStatus.GONE, detail="Event is sold out.")
    if event.extra.conditional and not is_min_tickets_met and not is_window_open:
        event.canceled = True
        await update_event(event)
        await refund_tickets(event_id)

        raise HTTPException(status_code=HTTPStatus.GONE, detail="Event canceled.")

    if not is_window_open:
        raise HTTPException(
            status_code=HTTPStatus.GONE, detail="Ticket closing date has passed."
        )

    return event


@events_api_router.post("")
@events_api_router.put("/{event_id}")
async def api_event_create(
    data: CreateEvent,
    wallet: WalletTypeInfo = Depends(require_admin_key),
    event_id: str | None = None,
) -> Event:
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

    return event


@events_api_router.put("/{event_id}/cancel")
async def api_event_cancel(
    event_id: str,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> Event:
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )

    if event.wallet != wallet.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your event.")
    event.canceled = True
    event = await update_event(event)
    await refund_tickets(event.id)

    return event


@events_api_router.delete("/{event_id}")
async def api_form_delete(
    event_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
) -> None:
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )

    if event.wallet != wallet.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your event.")

    await delete_event(event_id)
    await delete_event_tickets(event_id)


@events_api_router.get(
    "/{event_id}/tickets",
    response_model=list[PublicTicket],
)
async def api_event_tickets(event_id: str) -> list[Ticket]:
    return await get_event_tickets(event_id)


@tickets_api_router.get("")
async def api_tickets(
    all_wallets: bool = Query(False),
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> list[Ticket]:
    wallet_ids = [key_info.wallet.id]

    if all_wallets:
        user = await get_user(key_info.wallet.user)
        wallet_ids = user.wallet_ids if user else []

    return await get_tickets(wallet_ids)


@tickets_api_router.get("/{ticket_id}", response_model=PublicTicket)
async def api_get_ticket(ticket_id: str) -> Ticket:
    ticket = await get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Ticket does not exist."
        )
    event = await get_event(ticket.event)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )
    return ticket


@tickets_api_router.post("/{event_id}")
async def api_ticket_create(event_id: str, data: CreateTicket) -> TicketPaymentRequest:
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )

    if event.canceled:
        raise HTTPException(status_code=HTTPStatus.GONE, detail="Event is canceled.")

    if event.amount_tickets > 0 and event.sold >= event.amount_tickets:
        raise HTTPException(status_code=HTTPStatus.GONE, detail="Event is sold out.")

    name = data.name
    email = data.email
    promo_code = data.promo_code.upper() if data.promo_code else None
    refund_address = data.refund_address
    price = event.price_per_ticket
    extra: dict[str, Any] = {"tag": "events", "name": name, "email": email}

    if promo_code:
        # check if promo_code exists in event.extra.promo_codes
        if promo_code not in [pc.code for pc in event.extra.promo_codes]:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST, detail="Invalid promo code."
            )
        # get the promocode
        promo = next(pc for pc in event.extra.promo_codes if pc.code == promo_code)
        extra["promo_code"] = promo.code
        price = event.price_per_ticket * (1 - promo.discount_percent / 100)

    if event.currency != "sats":
        extra["fiat"] = True
        extra["currency"] = event.currency
        extra["fiatAmount"] = price
        extra["rate"] = await get_fiat_rate_satoshis(event.currency)

        price = await fiat_amount_as_satoshis(price, event.currency)

    payment = await create_invoice(
        wallet_id=event.wallet,
        amount=price,
        memo=f"{event_id}",
        extra=extra,
    )
    await create_ticket(
        payment_hash=payment.payment_hash,
        wallet=event.wallet,
        event=event.id,
        name=name,
        email=email,
        extra={
            "applied_promo_code": promo_code,
            "refund_address": refund_address,
            "sats_paid": int(price),
        },
    )

    return TicketPaymentRequest(
        payment_hash=payment.payment_hash, payment_request=payment.bolt11
    )


@tickets_api_router.websocket("/ws/{payment_hash}")
async def websocket_endpoint(payment_hash: str, websocket: WebSocket) -> None:
    await websocket.accept()
    queue: asyncio.Queue[Ticket] = asyncio.Queue()
    register_payment_listener(payment_hash, queue)
    disconnect_task: asyncio.Task | None = None
    payment_task: asyncio.Task | None = None

    try:
        ticket = await get_ticket(payment_hash)
        if ticket and ticket.paid:
            await websocket.send_json({"paid": True})
            return

        while True:
            disconnect_task = asyncio.create_task(websocket.receive_text())
            payment_task = asyncio.create_task(queue.get())
            done, pending = await asyncio.wait(
                {disconnect_task, payment_task}, return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()

            if disconnect_task in done:
                try:
                    disconnect_task.result()
                except WebSocketDisconnect:
                    pass
                break

            ticket = payment_task.result()
            await websocket.send_json({"paid": ticket.paid})
            if ticket.paid:
                break
    finally:
        for pending_task in (disconnect_task, payment_task):
            if pending_task and not pending_task.done():
                pending_task.cancel()
        deregister_payment_listener(payment_hash, queue)


@tickets_api_router.delete("/{ticket_id}")
async def api_ticket_delete(
    ticket_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
) -> None:
    ticket = await get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Ticket does not exist."
        )

    if ticket.wallet != wallet.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your ticket.")

    await delete_ticket(ticket_id)


@tickets_api_router.put("/register/{ticket_id}", response_model=PublicTicket)
async def api_event_register_ticket(ticket_id) -> Ticket:
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
    ticket = await update_ticket(ticket)
    return ticket
