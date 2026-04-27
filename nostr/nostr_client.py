"""
Bidirectional Nostr client for the events extension.

Connects to the nostrclient extension's internal WebSocket to publish
and subscribe to NIP-52 calendar events. Based on nostrmarket's
NostrClient pattern.
"""

import asyncio
import json
from asyncio import Queue
from collections import OrderedDict
from typing import Optional

from loguru import logger
from websocket import WebSocketApp

from lnbits.helpers import encrypt_internal_message, urlsafe_short_hash
from lnbits.settings import settings

from .event import NostrEvent

MAX_SEEN_EVENTS = 500


class NostrClient:
    def __init__(self):
        self.receive_event_queue: Queue = Queue()
        self.send_req_queue: Queue = Queue()
        self.ws: Optional[WebSocketApp] = None
        self.subscription_id = "events-" + urlsafe_short_hash()[:32]
        self.running = False
        self._seen_events: OrderedDict[str, None] = OrderedDict()

    @property
    def is_websocket_connected(self):
        if not self.ws:
            return False
        return self.ws.keep_running

    async def connect(self) -> WebSocketApp:
        relay_endpoint = encrypt_internal_message("relay", urlsafe=True)
        ws_url = (
            f"ws://localhost:{settings.port}"
            f"/nostrclient/api/v1/{relay_endpoint}"
        )

        logger.info("[EVENTS] Connecting to nostrclient WebSocket...")

        def on_open(_):
            logger.info("[EVENTS] Connected to nostrclient WebSocket")

        def on_message(_, message):
            try:
                self.receive_event_queue.put_nowait(message)
            except Exception as e:
                logger.error(f"[EVENTS] Failed to queue message: {e}")

        def on_error(_, error):
            logger.warning(f"[EVENTS] WebSocket error: {error}")

        def on_close(_, status_code, message):
            logger.warning(
                f"[EVENTS] WebSocket closed: {status_code} {message}"
            )
            self.receive_event_queue.put_nowait(
                ValueError("WebSocket closed")
            )

        ws = WebSocketApp(
            ws_url,
            on_message=on_message,
            on_open=on_open,
            on_close=on_close,
            on_error=on_error,
        )

        from threading import Thread

        wst = Thread(target=ws.run_forever)
        wst.daemon = True
        wst.start()

        return ws

    async def run_forever(self):
        self.running = True
        while self.running:
            try:
                if not self.is_websocket_connected:
                    self.ws = await self.connect()
                    await asyncio.sleep(5)

                req = await self.send_req_queue.get()
                assert self.ws
                self.ws.send(json.dumps(req))
            except Exception as ex:
                logger.warning(f"[EVENTS] NostrClient error: {ex}")
                await asyncio.sleep(60)

    def is_duplicate_event(self, event_id: str) -> bool:
        """Check if an event has been seen recently."""
        if event_id in self._seen_events:
            return True
        self._seen_events[event_id] = None
        if len(self._seen_events) > MAX_SEEN_EVENTS:
            self._seen_events.popitem(last=False)
        return False

    async def get_event(self):
        """Get next event from the receive queue."""
        value = await self.receive_event_queue.get()
        if isinstance(value, ValueError):
            raise value
        return value

    async def publish_nostr_event(self, e: NostrEvent):
        await self.send_req_queue.put(["EVENT", e.dict()])

    async def subscribe(self, filters: list[dict]):
        """Subscribe to events matching the given filters."""
        self.subscription_id = "events-" + urlsafe_short_hash()[:32]
        await self.send_req_queue.put(
            ["REQ", self.subscription_id] + filters
        )
        logger.info(
            f"[EVENTS] Subscribed to NIP-52 events "
            f"(sub: {self.subscription_id[:20]}...)"
        )

    async def unsubscribe(self):
        """Unsubscribe from current subscription."""
        await self.send_req_queue.put(["CLOSE", self.subscription_id])

    async def stop(self):
        await self.unsubscribe()
        self.running = False
        await asyncio.sleep(2)
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
