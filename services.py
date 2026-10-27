from __future__ import annotations

import smtplib
from asyncio.tasks import create_task
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Any
from urllib.parse import urlsplit

import httpx
from bolt11 import decode as bolt11_decode
from lnbits.core.crud.payments import get_standalone_payment
from lnbits.core.models.users import UserNotifications
from lnbits.core.services.lnurl import get_pr_from_lnurl
from lnbits.core.services.notifications import send_user_notification
from lnbits.core.services.payments import pay_invoice, update_pending_payment
from lnbits.helpers import is_valid_email_address
from lnbits.settings import settings
from loguru import logger

from .crud import (
    create_ticket_refund,
    get_closed_events,
    get_event,
    get_event_tickets,
    get_ticket_refund,
    mark_event_closed,
    purge_unpaid_tickets,
    update_event,
    update_ticket,
)
from .models import (
    Event,
    NotificationDeliveryResult,
    Ticket,
    TicketRefund,
    TicketResendResult,
    ensure_ticket_waves,
)


async def fetch_watchonly_config(api_key: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url=f"http://{settings.host}:{settings.port}/watchonly/api/v1/config",
            headers={"X-API-KEY": api_key},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_watchonly_wallets(api_key: str, network: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url=f"http://{settings.host}:{settings.port}/watchonly/api/v1/wallet",
            headers={"X-API-KEY": api_key},
            params={"network": network},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_watchonly_wallet(api_key: str, wallet_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url=f"http://{settings.host}:{settings.port}/watchonly/api/v1/wallet/{wallet_id}",
            headers={"X-API-KEY": api_key},
        )
        resp.raise_for_status()
        return resp.json()


async def get_satspay_charge(api_key: str, charge_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url=f"http://{settings.host}:{settings.port}/satspay/api/v1/charge/{charge_id}",
            headers={"X-API-KEY": api_key},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_core_onchain_wallets(api_key: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url=f"http://{settings.host}:{settings.port}/satspay/api/v1/onchain-wallets",
            headers={"X-API-KEY": api_key},
        )
        resp.raise_for_status()
        return resp.json()


async def create_satspay_charge(api_key: str, data: dict) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url=f"http://{settings.host}:{settings.port}/satspay/api/v1/charge",
            headers={"X-API-KEY": api_key},
            json=data,
        )
        if resp.status_code == 400:
            raise ValueError(resp.json().get("detail", "Cannot create SatsPay charge."))
        resp.raise_for_status()
        return resp.json()


async def set_ticket_paid(ticket: Ticket) -> Ticket:
    if ticket.paid:
        return ticket

    ticket.paid = True
    await update_ticket(ticket)

    event = await get_event(ticket.event)
    assert event, "Couldn't get event from ticket being paid"
    event.sold += 1
    event.close_processed = False
    ticket_waves = event.extra.ticket_waves or []
    if ticket_waves:
        selected_wave = next(
            (wave for wave in ticket_waves if wave.id == ticket.extra.ticket_wave_id),
            ticket_waves[0],
        )
        if selected_wave.amount_tickets > 0:
            selected_wave.amount_tickets -= 1
    elif event.amount_tickets > 0:
        event.amount_tickets -= 1
    await update_event(event)

    return ticket


def send_ticket_notification_in_background(ticket: Ticket) -> None:
    create_task(_send_ticket_notification(ticket))


async def _send_ticket_notification(ticket: Ticket) -> None:
    event = await get_event(ticket.event)
    if not event:
        logger.warning(f"Event {ticket.event} not found for ticket notification.")
        return

    await _deliver_ticket_notifications(ticket, event)


async def resend_ticket_email_notification(ticket: Ticket) -> TicketResendResult:
    event = await get_event(ticket.event)
    if not event:
        raise ValueError("Event does not exist.")
    if not settings.lnbits_email_notifications_enabled:
        raise ValueError("Email notifications are not enabled.")
    if not ticket.email:
        raise ValueError("Ticket does not have an email address.")
    return await _deliver_ticket_notifications(ticket, event)


def get_event_base_url() -> str:
    base_url = settings.lnbits_baseurl.rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Configure LNBITS_BASEURL with an absolute HTTP or HTTPS URL.")
    if parsed.query or parsed.fragment:
        raise ValueError("LNBITS_BASEURL must not include a query or fragment.")
    return base_url


def _ticket_notification_message(ticket: Ticket, event: Event) -> tuple[str, str]:
    ticket_url = _ticket_url(ticket)
    subject = (
        event.extra.notification_subject.strip()
        or f"Your ticket for '{event.name}' is ready"
    )
    body = (
        event.extra.notification_body.strip()
        or f"Your ticket for '{event.name}' is ready."
    )

    return subject, f"{body}\n\nOpen it here: {ticket_url}"


def _ticket_delivery_message(ticket: Ticket, event: Event, base_message: str) -> str:
    ticket_image_url = _ticket_image_url(ticket, event)
    if not ticket_image_url:
        return base_message

    return f"{base_message}\n\nTicket image: {ticket_image_url}"


def _ticket_email_html_message(ticket: Ticket, event: Event, base_message: str) -> str:
    text_message = _ticket_delivery_message(ticket, event, base_message)
    html_message = f"<p>{escape(text_message).replace(chr(10), '<br />')}</p>"
    ticket_image_url = _ticket_image_url(ticket, event)
    if not ticket_image_url:
        return html_message

    return (
        f"{html_message}"
        f'<p><img src="{escape(ticket_image_url, quote=True)}" alt="Ticket image" '
        'style="max-width: 200px; height: auto;" /></p>'
    )


def _ticket_notification_payload(ticket: Ticket, event: Event) -> tuple[str, str, str]:
    subject, base_message = _ticket_notification_message(ticket, event)
    text_message = _ticket_delivery_message(ticket, event, base_message)
    html_message = _ticket_email_html_message(ticket, event, base_message)
    return subject, text_message, html_message


def _supports_nostr_delivery(identifier: str | None) -> bool:
    return bool(identifier and "@" in identifier)


async def _deliver_ticket_notifications(
    ticket: Ticket, event: Event
) -> TicketResendResult:
    subject, text_message, html_message = _ticket_notification_payload(ticket, event)
    updated = False
    result = TicketResendResult(
        ticket=ticket,
        email=NotificationDeliveryResult(
            attempted=bool(
                event.extra.email_notifications
                and settings.lnbits_email_notifications_enabled
                and ticket.email
            )
        ),
        nostr=NotificationDeliveryResult(
            attempted=bool(
                event.extra.nostr_notifications
                and settings.is_nostr_notifications_configured()
                and ticket.extra.nostr_identifier
            )
        ),
    )

    if result.email.attempted:
        try:
            await _send_ticket_email_notification(
                [ticket.email], text_message, subject, html_message
            )
            ticket.extra.email_notification_sent = True
            result.email.sent = True
            updated = True
        except Exception as exc:
            logger.warning(f"Failed to email ticket {ticket.id}: {exc}")
            result.email.error = str(exc)

    if result.nostr.attempted and not _supports_nostr_delivery(
        ticket.extra.nostr_identifier
    ):
        result.nostr.error = "Only NIP-05 Nostr identifiers are supported."
    elif result.nostr.attempted:
        try:
            identifier = ticket.extra.nostr_identifier
            assert identifier is not None
            await _send_nostr_ticket_notification(identifier, text_message)
            ticket.extra.nostr_notification_sent = True
            result.nostr.sent = True
            updated = True
        except Exception as exc:
            logger.warning(f"Failed to send nostr DM for ticket {ticket.id}: {exc}")
            result.nostr.error = str(exc)

    if updated:
        result.ticket = await update_ticket(ticket)
    return result


async def _send_nostr_ticket_notification(identifier: str, message: str) -> None:
    await send_user_notification(
        UserNotifications(nostr_identifier=identifier),
        message,
        "text_message",
    )


async def _send_ticket_email_notification(
    to_emails: list[str],
    message: str,
    subject: str,
    html_message: str | None = None,
) -> None:
    if not settings.lnbits_email_notifications_enabled:
        raise ValueError("Email notifications are disabled")
    if not is_valid_email_address(settings.lnbits_email_notifications_email):
        raise ValueError(
            f"Invalid from email address: {settings.lnbits_email_notifications_email}"
        )
    if not to_emails:
        raise ValueError("No email addresses provided")
    for email in to_emails:
        if not is_valid_email_address(email):
            raise ValueError(f"Invalid email address: {email}")

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.lnbits_email_notifications_email
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject
    msg.attach(MIMEText(message, "plain"))
    if html_message:
        msg.attach(MIMEText(html_message, "html"))

    username = (
        settings.lnbits_email_notifications_username
        or settings.lnbits_email_notifications_email
    )
    with smtplib.SMTP(
        settings.lnbits_email_notifications_server,
        settings.lnbits_email_notifications_port,
    ) as smtp_server:
        smtp_server.starttls()
        smtp_server.login(username, settings.lnbits_email_notifications_password)
        smtp_server.sendmail(
            settings.lnbits_email_notifications_email,
            to_emails,
            msg.as_string(),
        )


def _ticket_url(ticket: Ticket) -> str:
    base_url = get_event_base_url()
    return f"{base_url}/events/ticket/{ticket.id}"


def _ticket_image_url(ticket: Ticket, event: Event) -> str | None:
    waves = ensure_ticket_waves(event)
    wave = next(
        (wave for wave in waves if wave.id == ticket.extra.ticket_wave_id),
        waves[0],
    )
    if not wave.use_ticket_image:
        return None

    base_url = get_event_base_url()
    return f"{base_url}/events/api/v1/qr/{ticket.id}"


async def refund_tickets(event_id: str) -> bool:
    """
    Refund tickets for an event that has not met the minimum ticket requirement.
    This function should be called when the event is closed and the minimum ticket
    condition is not met.
    """
    await purge_unpaid_tickets(event_id)
    tickets = await get_event_tickets(event_id)

    complete = True
    for ticket in tickets:
        if not ticket.paid:
            complete = False
            continue
        if ticket.extra.refunded:
            continue
        if ticket.extra.refund_address and ticket.extra.sats_paid:
            try:
                refund = await get_ticket_refund(ticket.id)
                if not refund:
                    payment_request = await get_pr_from_lnurl(
                        ticket.extra.refund_address, ticket.extra.sats_paid * 1000
                    )
                    refund = await create_ticket_refund(
                        TicketRefund(
                            id=ticket.id,
                            payment_request=payment_request,
                            payment_hash=bolt11_decode(payment_request).payment_hash,
                        )
                    )

                # Keep the same invoice across retries, including uncertain outcomes.
                payment = await get_standalone_payment(
                    refund.payment_hash, wallet_id=ticket.wallet
                )
                if payment:
                    if (
                        not payment.is_out
                        or payment.extra.get("ticket_id") != ticket.id
                    ):
                        raise ValueError("Refund payment does not match ticket.")
                    if not payment.success:
                        payment = await update_pending_payment(payment)
                else:
                    payment = await pay_invoice(
                        wallet_id=ticket.wallet,
                        payment_request=refund.payment_request,
                        max_sat=ticket.extra.sats_paid,
                        tag="events_refund",
                        extra={"ticket_id": ticket.id},
                    )
                if payment.success:
                    ticket.extra.refunded = True
                    await update_ticket(ticket)
                else:
                    complete = False
                    if payment.failed:
                        logger.warning(f"Refund for ticket {ticket.id} needs review.")
            except Exception as exc:
                complete = False
                logger.warning(
                    f"Could not complete refund for ticket {ticket.id}: "
                    f"{type(exc).__name__}: {exc}"
                )
    return complete


async def close_events() -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    for event in await get_closed_events():
        try:
            if (
                not event.canceled
                and event.closing_date < today
                and event.extra.conditional
                and event.sold < event.extra.min_tickets
            ):
                event.canceled = True
                await update_event(event)
            if event.canceled:
                complete = await refund_tickets(event.id)
            elif event.closing_date < today:
                await purge_unpaid_tickets(event.id)
                tickets = await get_event_tickets(event.id)
                complete = all(ticket.paid for ticket in tickets)
            else:
                continue
            if complete:
                await mark_event_closed(event)
        except Exception as exc:
            logger.warning(
                f"Could not close event {event.id}: {type(exc).__name__}: {exc}"
            )
