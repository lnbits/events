from __future__ import annotations

from asyncio.tasks import create_task

from lnbits.core.models.users import UserNotifications
from lnbits.core.services.nostr import send_nostr_dm
from lnbits.core.services.notifications import send_user_notification
from lnbits.settings import settings
from lnbits.utils.nostr import normalize_private_key, normalize_public_key
from lnurl import execute
from loguru import logger

from .crud import (
    get_event,
    get_event_tickets,
    purge_unpaid_tickets,
    update_event,
    update_ticket,
)
from .models import Ticket

DEFAULT_NOSTR_RELAYS = [
    "wss://relay.damus.io",
    "wss://relay.primal.net",
    "wss://relay.nostr.band",
]


async def set_ticket_paid(ticket: Ticket) -> Ticket:
    if ticket.paid:
        return ticket

    ticket.paid = True
    await update_ticket(ticket)

    event = await get_event(ticket.event)
    assert event, "Couldn't get event from ticket being paid"
    event.sold += 1
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

    ticket_url = _ticket_url(ticket)
    message = (
        f"{settings.lnbits_site_title}\n"
        f"Your ticket for '{event.name}' is ready.\n"
        f"Open it here: {ticket_url}"
    )
    updated = False

    if (
        event.extra.email_notifications
        and settings.lnbits_email_notifications_enabled
        and ticket.email
    ):
        try:
            await send_user_notification(
                UserNotifications(email_address=ticket.email),
                message,
                "text_message",
            )
            ticket.extra.email_notification_sent = True
            updated = True
        except Exception as exc:
            logger.warning(f"Failed to email ticket {ticket.id}: {exc}")

    if (
        event.extra.nostr_notifications
        and settings.is_nostr_notifications_configured()
        and ticket.extra.nostr_identifier
    ):
        try:
            await _send_nostr_ticket_notification(
                ticket.extra.nostr_identifier, message
            )
            ticket.extra.nostr_notification_sent = True
            updated = True
        except Exception as exc:
            logger.warning(f"Failed to send nostr DM for ticket {ticket.id}: {exc}")

    if updated:
        await update_ticket(ticket)


async def _send_nostr_ticket_notification(identifier: str, message: str) -> None:
    if "@" in identifier:
        await send_user_notification(
            UserNotifications(nostr_identifier=identifier),
            message,
            "text_message",
        )
        return

    private_key = normalize_private_key(settings.lnbits_nostr_notifications_private_key)
    public_key = normalize_public_key(identifier)
    await send_nostr_dm(private_key, public_key, message, DEFAULT_NOSTR_RELAYS)


def _ticket_url(ticket: Ticket) -> str:
    base_url = (ticket.extra.ticket_base_url or settings.lnbits_baseurl).rstrip("/")
    return f"{base_url}/events/ticket/{ticket.id}"


async def refund_tickets(event_id: str):
    """
    Refund tickets for an event that has not met the minimum ticket requirement.
    This function should be called when the event is closed and the minimum ticket
    condition is not met.
    """
    await purge_unpaid_tickets(event_id)
    tickets = await get_event_tickets(event_id)

    if not tickets:
        return

    for ticket in tickets:
        if ticket.extra.refunded:
            continue
        if ticket.paid and ticket.extra.refund_address and ticket.extra.sats_paid:
            try:
                res = await execute(
                    ticket.extra.refund_address, str(ticket.extra.sats_paid)
                )
                if res:
                    ticket.extra.refunded = True
                    await update_ticket(ticket)
            except Exception as e:
                logger.error(f"Error refunding ticket {ticket.id}: {e}")
