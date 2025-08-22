from datetime import date, datetime
from http import HTTPStatus

from fastapi import APIRouter, Depends, Request
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse

from .crud import get_event, get_ticket
from .services import refund_tickets

events_generic_router = APIRouter()


def events_renderer():
    return template_renderer(["events/templates"])


@events_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return events_renderer().TemplateResponse(
        "events/index.html", {"request": request, "user": user.json()}
    )


@events_generic_router.get("/{event_id}", response_class=HTMLResponse)
async def display(request: Request, event_id):
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )

    is_window_open = (
        date.today() < datetime.strptime(event.closing_date, "%Y-%m-%d").date()
    )
    is_min_tickets_met = (
        event.sold >= event.extra.min_tickets if event.extra.conditional else True
    )

    if event.amount_tickets < 1:
        return events_renderer().TemplateResponse(
            "events/error.html",
            {
                "request": request,
                "event_name": event.name,
                "event_error": "Sorry, tickets are sold out :(",
            },
        )
    if not is_window_open:
        return events_renderer().TemplateResponse(
            "events/error.html",
            {
                "request": request,
                "event_name": event.name,
                "event_error": "Sorry, ticket closing date has passed :(",
            },
        )
    if event.extra.conditional and not is_min_tickets_met and not is_window_open:
        await refund_tickets(event_id)

        return events_renderer().TemplateResponse(
            "events/error.html",
            {
                "request": request,
                "event_name": event.name,
                "event_error": "Sorry, minimum ticket requirement not met.",
            },
        )
    return events_renderer().TemplateResponse(
        "events/display.html",
        {
            "request": request,
            "event_id": event_id,
            "event_name": event.name,
            "event_info": event.info,
            "event_price": event.price_per_ticket,
            "event_banner": event.banner,
            "event_extra": event.extra.json(),
        },
    )


@events_generic_router.get("/ticket/{ticket_id}", response_class=HTMLResponse)
async def ticket(request: Request, ticket_id):
    ticket = await get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Ticket does not exist."
        )

    event = await get_event(ticket.event)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )

    return events_renderer().TemplateResponse(
        "events/ticket.html",
        {
            "request": request,
            "ticket_id": ticket_id,
            "ticket_name": event.name,
            "ticket_info": event.info,
        },
    )


@events_generic_router.get("/register/{event_id}", response_class=HTMLResponse)
async def register(request: Request, event_id):
    event = await get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Event does not exist."
        )

    return events_renderer().TemplateResponse(
        "events/register.html",
        {
            "request": request,
            "event_id": event_id,
            "event_name": event.name,
            "wallet_id": event.wallet,
        },
    )
