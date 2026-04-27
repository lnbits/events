import asyncio

from fastapi import APIRouter
from loguru import logger

from .crud import db
from .tasks import wait_for_paid_invoices
from .views import events_generic_router
from .views_api import events_api_router

events_ext: APIRouter = APIRouter(prefix="/events", tags=["Events"])
events_ext.include_router(events_generic_router)
events_ext.include_router(events_api_router)

events_static_files = [
    {
        "path": "/events/static",
        "name": "events_static",
    }
]

scheduled_tasks: list[asyncio.Task] = []

# Module-level NostrClient — None when nostrclient is unavailable
nostr_client = None


def events_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)

    global nostr_client
    if nostr_client:
        asyncio.get_event_loop().create_task(nostr_client.stop())


def events_start():
    from lnbits.tasks import create_permanent_unique_task

    task1 = create_permanent_unique_task("ext_events", wait_for_paid_invoices)
    scheduled_tasks.append(task1)

    async def _start_nostr_client():
        global nostr_client
        await asyncio.sleep(10)  # Wait for nostrclient to be ready
        try:
            from .nostr.nostr_client import NostrClient

            nostr_client = NostrClient()
            logger.info("[EVENTS] Starting NostrClient for NIP-52 sync")
            await nostr_client.run_forever()
        except Exception as e:
            logger.warning(f"[EVENTS] NostrClient failed to start: {e}")
            logger.info("[EVENTS] Events will work without Nostr sync")

    task2 = create_permanent_unique_task("ext_events_nostr", _start_nostr_client)
    scheduled_tasks.append(task2)

    async def _sync_nostr_events():
        global nostr_client
        await asyncio.sleep(15)  # Wait for NostrClient to connect
        if not nostr_client:
            logger.info("[EVENTS] No NostrClient, skipping Nostr sync")
            return
        try:
            from .nostr_sync import wait_for_nostr_events

            await wait_for_nostr_events(nostr_client)
        except Exception as e:
            logger.error(f"[EVENTS] Nostr sync task failed: {e}")

    task3 = create_permanent_unique_task(
        "ext_events_nostr_sync", _sync_nostr_events
    )
    scheduled_tasks.append(task3)


__all__ = ["db", "events_ext", "events_start", "events_static_files", "events_stop"]
