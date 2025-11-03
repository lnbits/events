from datetime import datetime

from fastapi import Query
from pydantic import BaseModel, EmailStr, root_validator


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
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    user_id: Optional[str] = None
    
    @root_validator
    def validate_identifiers(cls, values):
        # Ensure either (name AND email) OR user_id is provided
        name = values.get('name')
        email = values.get('email')
        user_id = values.get('user_id')
        
        if not user_id and not (name and email):
            raise ValueError("Either user_id or both name and email must be provided")
        if user_id and (name or email):
            raise ValueError("Cannot provide both user_id and name/email")
        return values


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
    name: Optional[str] = None
    email: Optional[str] = None
    user_id: Optional[str] = None
    registered: bool
    paid: bool
    time: datetime
    reg_timestamp: datetime
