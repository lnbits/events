"""Helpers that bridge event-mutation handlers to the Nostr publisher.

Lives in its own module so both `events_api_router` and any future router
can call it without importing through `views_api`, which would create an
import cycle (views_api -> nostr_hooks -> nostr_publisher -> models).
"""

from loguru import logger

from .crud import update_event
from .models import Event
from .nostr_publisher import publish_event_to_nostr


async def publish_or_delete_nostr_event(event: Event, *, delete: bool = False) -> None:
    """Publish or delete the NIP-52 calendar event for `event`.

    Pulls the wallet owner's pubkey/prvkey to sign with the user's identity.
    Failures are logged and swallowed so a Nostr outage doesn't break the
    HTTP flow that triggered the publish.
    """
    try:
        from lnbits.core.crud.users import get_account
        from lnbits.core.crud.wallets import get_wallet

        from . import nostr_client

        wallet_obj = await get_wallet(event.wallet)
        if not wallet_obj:
            return
        account = await get_account(wallet_obj.user)
        if not account or not account.pubkey or not account.prvkey:
            return

        nostr_event = await publish_event_to_nostr(
            nostr_client, event, account.pubkey, account.prvkey, delete=delete
        )
        if nostr_event and not delete:
            event.nostr_event_id = nostr_event.id
            event.nostr_event_created_at = nostr_event.created_at
            await update_event(event)
    except Exception as exc:
        logger.warning(f"[EVENTS] Nostr publish failed: {exc}")
