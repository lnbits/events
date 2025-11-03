# Events API Documentation

## Public Events Endpoint

### GET `/api/v1/events/public`

Retrieve all events in the database with read-only access. No authentication required.

**Authentication:** None required (public endpoint)

**Headers:**
```
None required
```

**Query Parameters:**
- None

**Response:**
```json
[
  {
    "id": "event_id",
    "wallet": "wallet_id",
    "name": "Event Name",
    "info": "Event description",
    "closing_date": "2024-12-31",
    "event_start_date": "2024-12-01",
    "event_end_date": "2024-12-02",
    "currency": "sat",
    "amount_tickets": 100,
    "price_per_ticket": 1000.0,
    "time": "2024-01-01T00:00:00Z",
    "sold": 0,
    "banner": null
  }
]
```

**Example Usage:**
```bash
curl http://your-lnbits-instance/events/api/v1/events/public
```

**Notes:**
- This endpoint allows read-only access to all events in the database
- No authentication required (truly public endpoint)
- Returns events ordered by creation time (newest first)
- Suitable for public event listings or read-only integrations

## Comparison with Existing Endpoints

| Endpoint | Authentication | Scope | Use Case |
|----------|---------------|-------|----------|
| `/api/v1/events` | Invoice Key | User's wallets only | Private event management |
| `/api/v1/events/public` | None | All events | Public event browsing | 