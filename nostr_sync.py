"""
Bidirectional Nostr sync for the events extension.

Subscribes to NIP-52 calendar events (kind 31922/31923) from relays
and upserts them into the local database. Enables federated event
discovery — events published by other LNbits instances or Nostr
clients appear in the local events listing.
"""

import json
from datetime import datetime, timezone

from loguru import logger

from .crud import create_event, db, get_event, update_event
from .models import CreateEvent, Event
from .nostr.nostr_client import NostrClient


async def process_nostr_message(nostr_client: NostrClient, message: str):
    """Process an incoming Nostr relay message."""
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return

    if not isinstance(data, list) or len(data) < 2:
        return

    msg_type = data[0]

    if msg_type == "EVENT" and len(data) >= 3:
        event_data = data[2]
        await _handle_calendar_event(nostr_client, event_data)
    elif msg_type == "EOSE":
        logger.debug("[EVENTS] End of stored events from relay")
    elif msg_type == "NOTICE":
        logger.info(f"[EVENTS] Relay notice: {data[1]}")


async def _handle_calendar_event(nostr_client: NostrClient, event_data: dict):
    """Handle an incoming NIP-52 calendar event (kind 31922 or 31923)."""
    kind = event_data.get("kind")
    if kind not in (31922, 31923):
        return

    event_id = event_data.get("id", "")
    if nostr_client.is_duplicate_event(event_id):
        return

    tags = {t[0]: t[1] for t in event_data.get("tags", []) if len(t) >= 2}
    tag_lists = {}
    for t in event_data.get("tags", []):
        if len(t) >= 2:
            tag_lists.setdefault(t[0], []).append(t[1])

    d_tag = tags.get("d")
    if not d_tag:
        return

    title = tags.get("title", "Untitled Event")
    start = tags.get("start")
    if not start:
        return

    end = tags.get("end")
    description = event_data.get("content", "")
    image = tags.get("image")
    location = tags.get("location")
    categories = tag_lists.get("t", [])

    # Check if we already have this event (by d-tag as our event ID
    # or by nostr_event_id)
    existing = await get_event(d_tag)
    if not existing:
        # Check by nostr_event_id
        existing = await db.fetchone(
            "SELECT * FROM events.events WHERE nostr_event_id = :nid",
            {"nid": event_id},
            Event,
        )

    if existing:
        # Update if the incoming event is newer
        incoming_created_at = event_data.get("created_at", 0)
        if (
            existing.nostr_event_created_at
            and incoming_created_at <= existing.nostr_event_created_at
        ):
            return  # We already have a newer version

        existing.name = title
        existing.info = description
        existing.event_start_date = start
        existing.event_end_date = end
        existing.banner = image
        existing.location = location
        existing.categories = categories
        existing.nostr_event_id = event_id
        existing.nostr_event_created_at = incoming_created_at
        await update_event(existing)
        logger.info(f"[EVENTS] Updated event from Nostr: {title}")
    else:
        # Create new event from Nostr
        # Events discovered from Nostr are auto-approved (they're already public)
        event = CreateEvent(
            wallet="",  # No wallet — discovered from Nostr, not ticketed locally
            name=title,
            info=description,
            event_start_date=start,
            event_end_date=end,
            banner=image,
            location=location,
            categories=categories,
            status="approved",
        )
        # Use the d-tag as the event ID for correlation
        from lnbits.db import Database

        new_event = Event(
            id=d_tag,
            wallet="",
            name=title,
            info=description,
            event_start_date=start,
            event_end_date=end,
            banner=image,
            location=location,
            categories=categories,
            status="approved",
            time=datetime.now(timezone.utc),
            nostr_event_id=event_id,
            nostr_event_created_at=event_data.get("created_at", 0),
        )
        try:
            await db.insert("events.events", new_event)
            logger.info(f"[EVENTS] Discovered event from Nostr: {title}")
        except Exception as e:
            # Likely duplicate key — skip
            logger.debug(f"[EVENTS] Skipped duplicate event: {e}")


async def wait_for_nostr_events(nostr_client: NostrClient):
    """
    Background task: subscribe to NIP-52 events and process them.
    """
    logger.info("[EVENTS] Starting Nostr event sync...")

    while True:
        try:
            # Subscribe to NIP-52 calendar events
            await nostr_client.subscribe([
                {"kinds": [31922, 31923]},
            ])

            # Process incoming events
            while True:
                message = await nostr_client.get_event()
                await process_nostr_message(nostr_client, message)

        except ValueError:
            # WebSocket closed — will reconnect
            logger.warning("[EVENTS] Nostr connection lost, resubscribing...")
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"[EVENTS] Nostr sync error: {e}")
            await asyncio.sleep(30)


import asyncio  # noqa: E402
