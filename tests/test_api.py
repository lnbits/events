import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from ..views_api import events_api_router
from ..models import Event
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_api_events_public():
    """Test the new public events API endpoint"""
    from fastapi import FastAPI
    
    app = FastAPI()
    app.include_router(events_api_router)
    
    # Mock the database
    with patch('events.crud.get_all_events') as mock_get_all_events:
        # Create mock events
        mock_events = [
            Event(
                id="test_event_1",
                wallet="test_wallet_1",
                name="Test Event 1",
                info="Test event description",
                closing_date="2024-12-31",
                event_start_date="2024-12-01",
                event_end_date="2024-12-02",
                currency="sat",
                amount_tickets=100,
                price_per_ticket=1000.0,
                time=datetime.now(timezone.utc),
                sold=0,
                banner=None
            ),
            Event(
                id="test_event_2",
                wallet="test_wallet_2",
                name="Test Event 2",
                info="Another test event",
                closing_date="2024-12-31",
                event_start_date="2024-12-03",
                event_end_date="2024-12-04",
                currency="sat",
                amount_tickets=50,
                price_per_ticket=500.0,
                time=datetime.now(timezone.utc),
                sold=0,
                banner=None
            )
        ]
        
        mock_get_all_events.return_value = mock_events
        
        client = TestClient(app)
        
        # Test the endpoint without any authentication
        response = client.get("/api/v1/events/public")
        
        # Verify the response
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == "test_event_1"
        assert data[1]["id"] == "test_event_2"
        assert data[0]["name"] == "Test Event 1"
        assert data[1]["name"] == "Test Event 2"


@pytest.mark.asyncio
async def test_get_all_events_crud():
    """Test the get_all_events CRUD function"""
    from events.crud import get_all_events
    
    with patch('events.crud.db.fetchall') as mock_fetchall:
        # Mock database response
        mock_events = [
            {
                "id": "test_event_1",
                "wallet": "test_wallet_1",
                "name": "Test Event 1",
                "info": "Test event description",
                "closing_date": "2024-12-31",
                "event_start_date": "2024-12-01",
                "event_end_date": "2024-12-02",
                "currency": "sat",
                "amount_tickets": 100,
                "price_per_ticket": 1000.0,
                "time": datetime.now(timezone.utc),
                "sold": 0,
                "banner": None
            }
        ]
        
        mock_fetchall.return_value = mock_events
        
        events = await get_all_events()
        
        # Verify the function was called with correct parameters
        mock_fetchall.assert_called_once_with(
            "SELECT * FROM events.events ORDER BY time DESC",
            model=Event,
        )
        
        # Verify the result
        assert len(events) == 1
        assert events[0]["id"] == "test_event_1" 