import asyncio

from fastapi import APIRouter
from loguru import logger

from .crud import db
from .views import events_generic_router
from .views_api import events_api_router, qr_api_router

events_ext: APIRouter = APIRouter(prefix="/events", tags=["Events"])
events_ext.include_router(events_generic_router)
events_ext.include_router(events_api_router)
events_ext.include_router(qr_api_router)

events_static_files = [
    {
        "path": "/events/static",
        "name": "events_static",
    }
]

scheduled_tasks: list[asyncio.Task] = []


def events_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)


def events_start():
    pass


__all__ = ["db", "events_ext", "events_start", "events_static_files", "events_stop"]
