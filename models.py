from datetime import datetime

from fastapi import Query
from pydantic import BaseModel, EmailStr


class CreateEvent(BaseModel):
    wallet: str
    name: str
    info: str
    closing_date: str
    event_start_date: str
    event_end_date: str
    currency: str = "sat"
    amount_tickets: int = Query(..., ge=0)
    price_per_ticket: float = Query(..., ge=0)
    banner: str | None = None


class CreateTicket(BaseModel):
    name: str
    email: EmailStr


class Event(BaseModel):
    id: str
    wallet: str
    name: str
    info: str
    closing_date: str
    event_start_date: str
    event_end_date: str
    currency: str
    amount_tickets: int
    price_per_ticket: float
    time: datetime
    sold: int = 0
    banner: str | None = None


class Ticket(BaseModel):
    id: str
    wallet: str
    event: str
    name: str
    email: str
    registered: bool
    paid: bool
    time: datetime
    reg_timestamp: datetime
