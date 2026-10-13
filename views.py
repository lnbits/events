from fastapi import APIRouter, Depends, HTTPException, Request
from lnbits.core.views.generic import index, index_public
from lnbits.decorators import check_account_id_exists
from lnbits.helpers import template_renderer
from starlette.responses import HTMLResponse

from .crud import get_event

events_generic_router = APIRouter()

events_generic_router.add_api_route(
    "/",
    methods=["GET"],
    endpoint=index,
    dependencies=[Depends(check_account_id_exists)],
)


async def event_public(request: Request, event_id: str) -> HTMLResponse:
    event = await get_event(event_id)
    return template_renderer(additional_folders=["events/templates"]).TemplateResponse(
        request,
        "event_public.html",
        {"public": True, "event": event.dict() if event else None},
    )


events_generic_router.add_api_route(
    "/{event_id}", methods=["GET"], endpoint=event_public
)

events_generic_router.add_api_route(
    "/ticket/{ticket_id}", methods=["GET"], endpoint=index_public
)

events_generic_router.add_api_route(
    "/register/{event_id}", methods=["GET"], endpoint=index_public
)

events_generic_router.add_api_route(
    "/basket/{basket_id}", methods=["GET"], endpoint=index_public
)
