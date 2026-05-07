import asyncio
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from lnbits.core.crud import get_user
from lnbits.core.crud.wallets import get_wallet
from lnbits.core.models import WalletTypeInfo
from lnbits.core.models.payments import CreateInvoice
from lnbits.core.services import create_payment_request
from lnbits.decorators import (
    require_admin_key,
    require_invoice_key,
)
from lnbits.settings import settings
from lnbits.utils.exchange_rates import (
    fiat_amount_as_satoshis,
    get_fiat_rate_satoshis,
)
from lnbits.utils.nostr import normalize_public_key

from .crud import (
    create_event,
    create_ticket,
    delete_event,
    delete_event_tickets,
    delete_ticket,
    get_event,
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


def _is_fiat_currency(currency: str | None) -> bool:
    return str(currency or "").lower() not in {"sat", "sats"}


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
async def api_ticket_create(
    event_id: str, data: CreateTicket, request: Request
) -> TicketPaymentRequest:
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
    nostr_identifier = data.nostr_identifier.strip() if data.nostr_identifier else None
    payment_method = (data.payment_method or "lightning").lower()
    if payment_method not in {"lightning", "fiat"}:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Unsupported payment method.",
        )
    if nostr_identifier and "@" not in nostr_identifier:
        try:
            nostr_identifier = normalize_public_key(nostr_identifier)
        except Exception as exc:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Invalid Nostr identifier.",
            ) from exc
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

    if payment_method == "fiat" and not event.allow_fiat:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Fiat payments are not enabled for this event.",
        )

    if _is_fiat_currency(event.currency):
        extra["fiat"] = True
        extra["currency"] = event.currency
        extra["fiatAmount"] = price
        extra["rate"] = await get_fiat_rate_satoshis(event.currency)

        if payment_method != "fiat":
            price = await fiat_amount_as_satoshis(price, event.currency)

    invoice_unit = event.currency
    fiat_provider = None
    if payment_method == "fiat":
        if not _is_fiat_currency(event.currency):
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Fiat checkout requires a fiat-denominated ticket price.",
            )
        wallet = await get_wallet(event.wallet)
        if not wallet:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Event wallet does not exist.",
            )
        providers = settings.get_fiat_providers_for_user(wallet.user)
        fiat_provider = data.fiat_provider or (providers[0] if providers else None)
        if not fiat_provider:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="No fiat payment provider configured for this event.",
            )
    else:
        invoice_unit = "sat"

    payment = await create_payment_request(
        wallet_id=event.wallet,
        invoice_data=CreateInvoice(
            out=False,
            amount=price,
            unit=invoice_unit,
            fiat_provider=fiat_provider,
            memo=f"{event_id}",
            extra=extra,
        ),
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
            "nostr_identifier": nostr_identifier,
            "ticket_base_url": str(request.base_url).rstrip("/"),
            "sats_paid": payment.sat,
        },
    )

    return TicketPaymentRequest(
        payment_hash=payment.payment_hash,
        payment_request=getattr(payment, "bolt11", None),
        fiat_payment_request=getattr(payment, "extra", {}).get("fiat_payment_request"),
        fiat_provider=getattr(payment, "fiat_provider", None) or fiat_provider,
        is_fiat=bool(getattr(payment, "fiat_provider", None) or fiat_provider),
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
