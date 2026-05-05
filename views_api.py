import asyncio
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from lnbits.core.crud import get_user
from lnbits.core.models import Account, WalletTypeInfo
from lnbits.core.services import create_invoice
from lnbits.decorators import (
    check_admin,
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
    get_all_events,
    get_event,
    get_event_tickets,
    get_events,
    get_pending_events,
    get_public_events,
    get_settings,
    get_ticket,
    get_tickets,
    get_tickets_by_user_id,
    purge_unpaid_tickets,
    update_event,
    update_settings,
    update_ticket,
)
from .models import (
    CreateEvent,
    CreateTicket,
    Event,
    EventsSettings,
    PublicEvent,
    PublicTicket,
    Ticket,
    TicketPaymentRequest,
)
from .services import refund_tickets
from .tasks import deregister_payment_listener, register_payment_listener

events_api_router = APIRouter(prefix="/api/v1/events")
tickets_api_router = APIRouter(prefix="/api/v1/tickets")


# Literal-prefix routes (/public, /all, /pending, /settings) MUST be declared
# before any "/{event_id}" route or FastAPI matches them as a path parameter.


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


@events_api_router.get("/public")
async def api_events_public() -> list[Event]:
    """Approved, non-canceled events for an anonymous public listing."""
    return await get_public_events()


@events_api_router.get("/all")
async def api_events_all(
    admin: Account = Depends(check_admin),
) -> list[Event]:
    """All events across all wallets. LNbits admin only."""
    return await get_all_events()


@events_api_router.get("/pending")
async def api_events_pending(
    admin: Account = Depends(check_admin),
) -> list[Event]:
    """Proposed events awaiting admin approval. LNbits admin only."""
    return await get_pending_events()


@events_api_router.get("/settings")
async def api_get_settings(
    admin: Account = Depends(check_admin),
) -> EventsSettings:
    return await get_settings()


@events_api_router.put("/settings")
async def api_update_settings(
    data: EventsSettings,
    admin: Account = Depends(check_admin),
) -> EventsSettings:
    return await update_settings(data)


@events_api_router.get("/{event_id}", response_model=PublicEvent)
async def api_get_event(event_id: str) -> Event:
    """Public event detail used by display.vue.

    For approved events we run the upstream sold-out / closing-window /
    conditional gates. For non-approved events (proposed / rejected) we
    return the trimmed PublicEvent with status set so the SFC can render
    the pending-approval banner without a separate request.
    """
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )

    if event.status != "approved":
        # Proposed/rejected events are not yet ticketable; skip ticket gates.
        return event

    await purge_unpaid_tickets(event_id)

    # closing_date is filled in by create_event (defaults to end_date or
    # start_date) but the field is typed Optional, so guard for the typechecker.
    closing_date = (
        event.closing_date or event.event_end_date or event.event_start_date
    )
    is_window_open = datetime.now(timezone.utc) < datetime.strptime(
        closing_date, "%Y-%m-%d"
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
async def api_event_create(
    data: CreateEvent,
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> Event:
    """Create a new event.

    Anyone with a wallet invoice key can submit. Non-LNbits-admins land in
    `proposed` status unless `auto_approve` is enabled in extension settings.
    """
    if not data.wallet:
        data.wallet = wallet.wallet.id

    from lnbits.settings import settings

    ext_settings = await get_settings()
    user_id = wallet.wallet.user
    is_admin = (
        user_id == settings.super_user
        or user_id in settings.lnbits_admin_users
    )
    if not is_admin and not ext_settings.auto_approve:
        data.status = "proposed"

    return await create_event(data)


@events_api_router.put("/{event_id}")
async def api_event_update(
    event_id: str,
    data: CreateEvent,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> Event:
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
    return await update_event(event)


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


@events_api_router.put("/{event_id}/approve")
async def api_event_approve(
    event_id: str,
    admin: Account = Depends(check_admin),
) -> Event:
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )
    if event.status != "proposed":
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Event is already {event.status}.",
        )
    event.status = "approved"
    return await update_event(event)


@events_api_router.put("/{event_id}/reject")
async def api_event_reject(
    event_id: str,
    admin: Account = Depends(check_admin),
) -> Event:
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )
    if event.status != "proposed":
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Event is already {event.status}.",
        )
    event.status = "rejected"
    return await update_event(event)


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


@tickets_api_router.get("/user/{user_id}")
async def api_tickets_by_user_id(user_id: str) -> list[Ticket]:
    """Tickets bound to an LNbits user_id (used by external integrations).

    Declared before /{ticket_id} so FastAPI matches the literal `/user/`
    prefix instead of treating "user" as a ticket id.
    """
    return await get_tickets_by_user_id(user_id)


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
async def api_ticket_create(
    event_id: str, data: CreateTicket
) -> TicketPaymentRequest:
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )
    if event.status != "approved":
        raise HTTPException(
            status_code=HTTPStatus.GONE,
            detail="Event is not yet open for tickets.",
        )
    if event.canceled:
        raise HTTPException(status_code=HTTPStatus.GONE, detail="Event is canceled.")
    if event.amount_tickets > 0 and event.sold >= event.amount_tickets:
        raise HTTPException(status_code=HTTPStatus.GONE, detail="Event is sold out.")

    if data.user_id:
        return await _create_user_id_ticket(event, data.user_id)
    return await _create_named_ticket(event, data)


async def _create_named_ticket(
    event: Event, data: CreateTicket
) -> TicketPaymentRequest:
    name = data.name
    email = data.email
    promo_code = data.promo_code.upper() if data.promo_code else None
    refund_address = data.refund_address
    price = event.price_per_ticket
    extra: dict[str, Any] = {"tag": "events", "name": name, "email": email}

    if promo_code:
        if promo_code not in [pc.code for pc in event.extra.promo_codes]:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST, detail="Invalid promo code."
            )
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
        memo=f"{event.id}",
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


async def _create_user_id_ticket(
    event: Event, user_id: str
) -> TicketPaymentRequest:
    price = event.price_per_ticket
    extra: dict[str, Any] = {"tag": "events", "user_id": user_id}

    if event.currency != "sats":
        price = await fiat_amount_as_satoshis(event.price_per_ticket, event.currency)
        extra["fiat"] = True
        extra["currency"] = event.currency
        extra["fiatAmount"] = event.price_per_ticket
        extra["rate"] = await get_fiat_rate_satoshis(event.currency)

    payment = await create_invoice(
        wallet_id=event.wallet,
        amount=price,
        memo=f"{event.id}",
        extra=extra,
    )
    await create_ticket(
        payment_hash=payment.payment_hash,
        wallet=event.wallet,
        event=event.id,
        user_id=user_id,
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


@tickets_api_router.put("/register/{ticket_id}")
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
