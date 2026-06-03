import asyncio
from datetime import datetime, timezone
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from typing import Any

import pyqrcode  # type: ignore[import-untyped]
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from lnbits.core.crud import get_standalone_payment, get_user
from lnbits.core.crud.assets import get_public_asset
from lnbits.core.crud.wallets import get_wallet
from lnbits.core.models import WalletTypeInfo
from lnbits.core.models.payments import CreateInvoice
from lnbits.core.services import create_payment_request
from lnbits.db import Filters, Page
from lnbits.decorators import (
    parse_filters,
    require_admin_key,
    require_invoice_key,
)
from lnbits.helpers import generate_filter_params_openapi
from lnbits.settings import settings
from lnbits.tasks import internal_invoice_queue_put
from lnbits.utils.exchange_rates import (
    fiat_amount_as_satoshis,
    get_fiat_rate_satoshis,
    satoshis_amount_as_fiat,
)
from PIL import Image, ImageDraw

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
    get_tickets_paginated,
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
    TicketFilters,
    TicketPaymentRequest,
    TicketResendResult,
    ensure_ticket_waves,
    get_active_ticket_waves,
)
from .services import (
    fetch_onchain_address,
    fetch_watchonly_config,
    fetch_watchonly_wallet,
    fetch_watchonly_wallets,
    refund_tickets,
    resend_ticket_email_notification,
)
from .tasks import deregister_payment_listener, register_payment_listener

events_api_router = APIRouter(prefix="/api/v1/events")
tickets_api_router = APIRouter(prefix="/api/v1/tickets")
qr_api_router = APIRouter(prefix="/api/v1")
tickets_filters = parse_filters(TicketFilters)


async def _get_watchonly_status(wallet) -> dict[str, Any]:
    try:
        config = await fetch_watchonly_config(wallet.inkey)
        network = config.get("network")
        if not network:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Watchonly extension returned an invalid network.",
            )
        wallets = await fetch_watchonly_wallets(wallet.inkey, network)
    except HTTPException:
        raise
    except Exception as exc:
        return {
            "available": False,
            "message": f"Watchonly extension is not reachable: {exc!s}",
            "network": None,
            "wallets": [],
            "mempool_endpoint": None,
        }
    return {
        "available": True,
        "message": None,
        "network": network,
        "wallets": wallets,
        "mempool_endpoint": config.get("mempool_endpoint"),
    }


async def _validate_watchonly_settings(
    *,
    wallet,
    onchain_enabled: bool,
    onchain_wallet_id: str | None,
) -> dict[str, Any]:
    if not onchain_enabled:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Onchain payments are not enabled for this event.",
        )
    if not onchain_wallet_id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="No watchonly wallet configured for onchain payments.",
        )
    status = await _get_watchonly_status(wallet)
    if not status["available"]:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=status["message"] or "Watchonly extension is not available.",
        )
    try:
        watch_wallet = await fetch_watchonly_wallet(wallet.inkey, onchain_wallet_id)
    except Exception as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Cannot access watchonly wallet: {exc!s}",
        ) from exc
    if watch_wallet.get("network") != status["network"]:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Watchonly wallet network does not match user watchonly config.",
        )
    return {
        "watch_wallet": watch_wallet,
        "network": status["network"],
        "mempool_endpoint": status["mempool_endpoint"],
    }


def _is_fiat_currency(currency: str | None) -> bool:
    return str(currency or "").lower() not in {"sat", "sats"}


def make_qr_png(data: str, size: int = 235, border: int = 4) -> Image.Image:
    qr = pyqrcode.create(data)
    matrix = qr.code
    modules = len(matrix)

    total_modules = modules + border * 2
    box_size = max(1, size // total_modules)
    img_size = total_modules * box_size

    img = Image.new("RGBA", (img_size, img_size), "white")
    draw = ImageDraw.Draw(img)

    for y, row in enumerate(matrix):
        for x, cell in enumerate(row):
            if cell:
                x0 = (x + border) * box_size
                y0 = (y + border) * box_size
                draw.rectangle(
                    [x0, y0, x0 + box_size - 1, y0 + box_size - 1],
                    fill="black",
                )

    if img_size != size:
        img = img.resize((size, size), Image.Resampling.NEAREST)

    return img


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


@events_api_router.get("/onchain/status")
async def api_onchain_status(
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> dict[str, Any]:
    return await _get_watchonly_status(wallet.wallet)


@events_api_router.get("/{event_id}", response_model=PublicEvent)
async def api_get_event(event_id: str) -> Event:
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )
    await purge_unpaid_tickets(event_id)

    today = datetime.now(timezone.utc).date()
    active_waves = get_active_ticket_waves(event, today)
    is_sales_closed = today > datetime.strptime(event.closing_date, "%Y-%m-%d").date()
    is_min_tickets_met = (
        event.sold >= event.extra.min_tickets if event.extra.conditional else True
    )
    if event.amount_tickets < 1:
        raise HTTPException(status_code=HTTPStatus.GONE, detail="Event is sold out.")
    if event.extra.conditional and not is_min_tickets_met and is_sales_closed:
        event.canceled = True
        await update_event(event)
        await refund_tickets(event_id)

        raise HTTPException(status_code=HTTPStatus.GONE, detail="Event canceled.")

    if not active_waves:
        raise HTTPException(
            status_code=HTTPStatus.GONE,
            detail=(
                "Ticket closing date has passed."
                if is_sales_closed
                else "No ticket wave is currently open."
            ),
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
        event = Event(
            **{
                **event.dict(),
                **data.dict(),
                "id": event.id,
                "wallet": event.wallet,
                "time": event.time,
                "sold": event.sold,
                "canceled": event.canceled,
            }
        )
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


@tickets_api_router.get(
    "/paginated",
    summary="Get paginated list of tickets",
    openapi_extra=generate_filter_params_openapi(TicketFilters),
    response_model=Page[Ticket],
)
async def api_tickets_paginated(
    all_wallets: bool = Query(False),
    filters: Filters = Depends(tickets_filters),
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> Page[Ticket]:
    wallet_ids = [key_info.wallet.id]

    if all_wallets:
        user = await get_user(key_info.wallet.user)
        wallet_ids = user.wallet_ids if user else []

    if not filters.sortby:
        filters.sortby = "time"
    if not filters.direction:
        filters.direction = "desc"

    return await get_tickets_paginated(wallet_ids, filters)


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


@qr_api_router.get("/qr/{ticket_id}", response_class=StreamingResponse)
async def api_ticket_qr(ticket_id: str):
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

    waves = ensure_ticket_waves(event)
    wave = next(
        (wave for wave in waves if wave.id == ticket.extra.ticket_wave_id),
        waves[0],
    )

    qr_img = make_qr_png(f"ticket://{ticket_id}", size=157)
    output = BytesIO()

    if not wave.use_ticket_image:
        qr_img.save(output, format="PNG")
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="image/png",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    background_bytes = None
    if wave.ticket_image_id:
        asset = await get_public_asset(wave.ticket_image_id)
        if asset:
            background_bytes = asset.data

    if background_bytes:
        ticket_image = Image.open(BytesIO(background_bytes)).convert("RGBA")
    else:
        default_template = (
            Path(__file__).resolve().parent / "static" / "image" / "ticket.jpg"
        )
        ticket_image = Image.open(default_template).convert("RGBA")

    ticket_image.paste(qr_img, (122, 505))
    ticket_image.save(output, format="PNG")
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="image/png",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


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

    if event.amount_tickets < 1:
        raise HTTPException(status_code=HTTPStatus.GONE, detail="Event is sold out.")

    name = data.name
    email = data.email
    promo_code = data.promo_code.upper() if data.promo_code else None
    refund_address = data.refund_address
    nostr_identifier = data.nostr_identifier.strip() if data.nostr_identifier else None
    payment_method = (data.payment_method or "lightning").lower()
    if payment_method not in {"lightning", "fiat", "onchain"}:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Unsupported payment method.",
        )
    if nostr_identifier and "@" not in nostr_identifier:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Only NIP-05 Nostr identifiers are supported.",
        )
    active_waves = get_active_ticket_waves(event)
    if not active_waves:
        raise HTTPException(
            status_code=HTTPStatus.GONE, detail="No ticket wave is currently open."
        )

    selected_wave = None
    if data.ticket_wave_id:
        selected_wave = next(
            (wave for wave in active_waves if wave.id == data.ticket_wave_id),
            None,
        )
        if not selected_wave:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Invalid ticket wave selected.",
            )
    elif len(active_waves) == 1:
        selected_wave = active_waves[0]
    else:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Please select a ticket wave.",
        )

    price = selected_wave.price_per_ticket
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
        price = selected_wave.price_per_ticket * (1 - promo.discount_percent / 100)

    if payment_method == "fiat" and not selected_wave.allow_fiat:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Fiat payments are not enabled for this event.",
        )

    if _is_fiat_currency(selected_wave.currency):
        extra["fiat"] = True
        extra["currency"] = selected_wave.currency
        extra["fiatAmount"] = price
        extra["rate"] = await get_fiat_rate_satoshis(selected_wave.currency)

        if payment_method != "fiat":
            price = await fiat_amount_as_satoshis(price, selected_wave.currency)

    invoice_unit = selected_wave.currency
    fiat_amount = price
    fiat_provider = None
    onchain_address = None
    onchain_mempool_endpoint = None
    onchain_amount_sat = None

    if payment_method == "fiat":
        if _is_fiat_currency(selected_wave.currency):
            invoice_unit = selected_wave.currency
        else:
            invoice_unit = selected_wave.fiat_currency
            fiat_amount = await satoshis_amount_as_fiat(price, invoice_unit)
            extra["fiat"] = True
            extra["currency"] = invoice_unit
            extra["fiatAmount"] = fiat_amount
            extra["rate"] = await get_fiat_rate_satoshis(invoice_unit)
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
    elif payment_method == "onchain":
        invoice_unit = "sat"
        onchain_amount_sat = int(price)
        wallet_record = await get_wallet(event.wallet)
        if not wallet_record:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Event wallet does not exist.",
            )
        validation = await _validate_watchonly_settings(
            wallet=wallet_record,
            onchain_enabled=event.extra.onchain_enabled,
            onchain_wallet_id=event.extra.onchain_wallet_id,
        )
        address_data = await fetch_onchain_address(
            wallet_record.inkey, event.extra.onchain_wallet_id or ""
        )
        onchain_address = address_data.get("address")
        onchain_mempool_endpoint = validation.get("mempool_endpoint")
    else:
        invoice_unit = "sat"

    if payment_method == "onchain":
        payment = await create_payment_request(
            wallet_id=event.wallet,
            invoice_data=CreateInvoice(
                out=False,
                amount=float(onchain_amount_sat or 0),
                unit="sat",
                internal=True,
                labels=["onchain"],
                memo=f"{event_id}",
                extra=extra,
            ),
        )
    else:
        payment = await create_payment_request(
            wallet_id=event.wallet,
            invoice_data=CreateInvoice(
                out=False,
                amount=fiat_amount if payment_method == "fiat" else price,
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
            "ticket_wave_id": selected_wave.id,
            "ticket_wave_title": selected_wave.title,
            "refund_address": refund_address,
            "nostr_identifier": nostr_identifier,
            "ticket_base_url": str(request.base_url).rstrip("/"),
            "sats_paid": (
                onchain_amount_sat if payment_method == "onchain" else payment.sat
            ),
            "onchain": payment_method == "onchain",
        },
    )

    return TicketPaymentRequest(
        payment_hash=payment.payment_hash,
        payment_request=getattr(payment, "bolt11", None),
        fiat_payment_request=getattr(payment, "extra", {}).get("fiat_payment_request"),
        fiat_provider=getattr(payment, "fiat_provider", None) or fiat_provider,
        is_fiat=bool(getattr(payment, "fiat_provider", None) or fiat_provider),
        onchain_address=onchain_address,
        onchain_mempool_endpoint=onchain_mempool_endpoint,
        onchain_amount_sat=onchain_amount_sat,
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


@tickets_api_router.put("/{payment_hash}/onchain-confirm")
async def api_ticket_onchain_confirm(
    payment_hash: str,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> Ticket:
    ticket = await get_ticket(payment_hash)
    if not ticket:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Ticket does not exist."
        )
    if ticket.wallet != wallet.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your ticket.")
    if ticket.paid:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="Ticket already paid."
        )
    if not ticket.extra.onchain:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Ticket is not an onchain payment.",
        )
    payment = await get_standalone_payment(payment_hash)
    if not payment:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Payment does not exist."
        )
    await internal_invoice_queue_put(payment_hash)
    return ticket


@tickets_api_router.post("/{ticket_id}/resend-email", response_model=TicketResendResult)
async def api_ticket_resend_email(
    ticket_id: str,
    request: Request,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> TicketResendResult:
    ticket = await get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Ticket does not exist."
        )

    if ticket.wallet != wallet.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your ticket.")

    if not ticket.paid:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Only paid tickets can be resent by email.",
        )

    try:
        return await resend_ticket_email_notification(
            ticket, str(request.base_url).rstrip("/")
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)
        ) from exc


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
