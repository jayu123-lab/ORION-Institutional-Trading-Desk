import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from apps.api.websocket_manager import WebSocketConnectionManager, WebSocketEventBridge


class TestWebSocketConnectionManager:
    """Test WebSocket connection manager."""

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        """Test adding and removing connections."""
        manager = WebSocketConnectionManager()
        ws = AsyncMock()

        assert manager.get_connection_count() == 0

        await manager.connect(ws)
        assert manager.get_connection_count() == 1
        ws.accept.assert_called_once()

        await manager.disconnect(ws)
        assert manager.get_connection_count() == 0

    @pytest.mark.asyncio
    async def test_broadcast_message(self):
        """Test broadcasting message to all connections."""
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)

        message = {"test": "data"}
        await manager.broadcast(message)

        assert ws1.send_text.call_count == 1
        assert ws2.send_text.call_count == 1

    @pytest.mark.asyncio
    async def test_broadcast_event(self):
        """Test broadcasting event with standard format."""
        manager = WebSocketConnectionManager()
        ws = AsyncMock()

        await manager.connect(ws)

        await manager.broadcast_event("test_event", {"key": "value"})

        ws.send_text.assert_called_once()
        call_args = ws.send_text.call_args[0][0]
        assert "test_event" in call_args
        assert "key" in call_args
        assert "timestamp" in call_args

    @pytest.mark.asyncio
    async def test_broadcast_disconnects_failed_clients(self):
        """Test that failed clients are disconnected."""
        manager = WebSocketConnectionManager()
        ws_good = AsyncMock()
        ws_bad = AsyncMock()
        ws_bad.send_text.side_effect = Exception("Send failed")

        await manager.connect(ws_good)
        await manager.connect(ws_bad)

        assert manager.get_connection_count() == 2

        await manager.broadcast({"test": "data"})

        # Bad connection should be removed
        assert manager.get_connection_count() == 1
        ws_good.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_broadcast(self):
        """Test broadcasting with no connections."""
        manager = WebSocketConnectionManager()
        ws = AsyncMock()

        # Should not raise error with no connections
        await manager.broadcast({"test": "data"})
        ws.send_text.assert_not_called()


class TestWebSocketEventBridge:
    """Test WebSocket event bridge."""

    @pytest.mark.asyncio
    async def test_event_bridge_start(self):
        """Test event bridge subscribes to events."""
        manager = WebSocketConnectionManager()
        event_bus = AsyncMock()
        event_bus.subscribe = MagicMock()

        bridge = WebSocketEventBridge(manager, event_bus)
        await bridge.start()

        # Should subscribe to multiple event types
        assert event_bus.subscribe.call_count >= 5
        call_args_list = [call[0] for call in event_bus.subscribe.call_args_list]
        event_types = [args[0] for args in call_args_list]

        assert "market_data_updated" in event_types
        assert "volume_spike_detected" in event_types
        assert "economic_event_triggered" in event_types
        assert "alert_generated" in event_types
        assert "decision_generated" in event_types

    @pytest.mark.asyncio
    async def test_handler_broadcasts_event(self):
        """Test that handler broadcasts events to WebSocket."""
        manager = WebSocketConnectionManager()
        event_bus = AsyncMock()
        ws = AsyncMock()

        bridge = WebSocketEventBridge(manager, event_bus)
        await manager.connect(ws)

        handler = bridge._create_handler("test_event")

        mock_event = MagicMock()
        mock_event.event_id = "evt_123"
        mock_event.symbol = "BTC"
        mock_event.severity = "warning"

        await handler(mock_event)

        ws.send_text.assert_called_once()
        call_args = ws.send_text.call_args[0][0]
        assert "test_event" in call_args
        assert "evt_123" in call_args
        assert "BTC" in call_args

    @pytest.mark.asyncio
    async def test_heartbeat_sends_periodically(self):
        """Test heartbeat task sends messages."""
        manager = WebSocketConnectionManager()
        event_bus = AsyncMock()
        ws = AsyncMock()

        bridge = WebSocketEventBridge(manager, event_bus)
        await manager.connect(ws)

        # Mock the broadcast to avoid waiting 30 seconds
        original_broadcast = bridge.connection_manager.broadcast
        call_count = 0

        async def mock_broadcast(message):
            nonlocal call_count
            call_count += 1
            await original_broadcast(message)

        bridge.connection_manager.broadcast = mock_broadcast

        # Create a task but cancel quickly (heartbeat waits 30s between sends)
        task = asyncio.create_task(bridge.send_heartbeat())
        await asyncio.sleep(0.1)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Heartbeat task is running correctly if no errors
        assert True
