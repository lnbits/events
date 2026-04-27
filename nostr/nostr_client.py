"""
Publish-only Nostr client for the events extension.

Connects to the nostrclient extension's internal WebSocket to publish
NIP-52 calendar events. No subscription/receive capabilities — this
is a stripped-down version of nostrmarket's NostrClient.
"""

import asyncio
import json
from asyncio import Queue
from typing import Optional

from loguru import logger
from websocket import WebSocketApp

from lnbits.helpers import encrypt_internal_message
from lnbits.settings import settings

from .event import NostrEvent


class NostrClient:
    def __init__(self):
        self.send_req_queue: Queue = Queue()
        self.ws: Optional[WebSocketApp] = None
        self.running = False

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
            # Log relay responses (OK, NOTICE) but don't process
            logger.debug(f"[EVENTS] Relay response: {message[:200]}")

        def on_error(_, error):
            logger.warning(f"[EVENTS] WebSocket error: {error}")

        def on_close(_, status_code, message):
            logger.warning(
                f"[EVENTS] WebSocket closed: {status_code} {message}"
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

    async def publish_nostr_event(self, e: NostrEvent):
        await self.send_req_queue.put(["EVENT", e.dict()])

    async def stop(self):
        self.running = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
