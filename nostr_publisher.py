"""
NIP-52 calendar event publishing for the events extension.

Builds kind 31922 (date-based) calendar events from the Event model,
signs them with the event creator's Account keypair, and publishes
via the NostrClient to nostrclient relays.

Reference: https://github.com/nostr-protocol/nips/blob/master/52.md
"""

import time
from typing import Optional

import coincurve
from loguru import logger

from .models import Event
from .nostr.event import NostrEvent


def build_nip52_event(event: Event, pubkey: str) -> NostrEvent:
    """
    Convert an Event model to a NIP-52 kind 31922 (date-based) calendar event.

    Tags:
      d       - event.id (addressable identifier)
      title   - event.name
      start   - event.event_start_date (ISO date string)
      end     - event.event_end_date (optional)
      image   - event.banner (optional)
    Content:  event.info (description)
    """
    tags = [
        ["d", event.id],
        ["title", event.name],
        ["start", event.event_start_date],
    ]

    if event.event_end_date:
        tags.append(["end", event.event_end_date])
    if event.banner:
        tags.append(["image", event.banner])
    if event.location:
        tags.append(["location", event.location])
    for cat in (event.categories or []):
        tags.append(["t", cat])

    nostr_event = NostrEvent(
        pubkey=pubkey,
        created_at=int(time.time()),
        kind=31922,
        tags=tags,
        content=event.info or "",
    )
    nostr_event.id = nostr_event.event_id
    return nostr_event


def build_nip52_delete_event(event: Event, pubkey: str) -> NostrEvent:
    """
    Build a kind 5 delete event for a published NIP-52 calendar event.

    Uses an 'a' tag to reference the parameterized replaceable event
    (kind 31922) per NIP-09.
    """
    nostr_event = NostrEvent(
        pubkey=pubkey,
        created_at=int(time.time()),
        kind=5,
        tags=[
            ["a", f"31922:{pubkey}:{event.id}"],
        ],
        content="Event canceled",
    )
    nostr_event.id = nostr_event.event_id
    return nostr_event


def sign_nostr_event(nostr_event: NostrEvent, private_key_hex: str) -> None:
    """Sign a NostrEvent in-place using Schnorr signature."""
    privkey = coincurve.PrivateKey(bytes.fromhex(private_key_hex))
    sig = privkey.sign_schnorr(bytes.fromhex(nostr_event.id))
    nostr_event.sig = sig.hex()


async def publish_event_to_nostr(
    nostr_client,
    event: Event,
    account_pubkey: str,
    account_prvkey: str,
    delete: bool = False,
) -> Optional[NostrEvent]:
    """
    Build, sign, and publish a NIP-52 calendar event (or delete event).

    Returns the published NostrEvent for metadata storage, or None on failure.
    """
    if not nostr_client:
        logger.debug("[EVENTS] No NostrClient available, skipping publish")
        return None

    try:
        if delete:
            nostr_event = build_nip52_delete_event(event, account_pubkey)
        else:
            nostr_event = build_nip52_event(event, account_pubkey)

        sign_nostr_event(nostr_event, account_prvkey)
        await nostr_client.publish_nostr_event(nostr_event)

        logger.info(
            f"[EVENTS] Published NIP-52 {'delete' if delete else 'calendar'} "
            f"event: {nostr_event.id[:16]}... (kind {nostr_event.kind})"
        )
        return nostr_event

    except Exception as e:
        logger.warning(f"[EVENTS] Failed to publish to Nostr: {e}")
        return None
