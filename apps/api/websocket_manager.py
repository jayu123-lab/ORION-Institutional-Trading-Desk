import asyncio
import json
import logging
from typing import Set
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

logger = logging.getLogger(__name__)


class WebSocketConnectionManager:
    """Manages WebSocket connections and broadcasts events to connected clients."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        """Accept a WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket."""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return

        message["timestamp"] = datetime.utcnow().isoformat() + "Z"
        message_json = json.dumps(message)

        disconnected = set()
        async with self._lock:
            for connection in self.active_connections:
                try:
                    await connection.send_text(message_json)
                except Exception as e:
                    logger.error(f"Error sending WebSocket message: {e}")
                    disconnected.add(connection)

        for conn in disconnected:
            await self.disconnect(conn)

    async def broadcast_event(self, event_type: str, data: dict):
        """Broadcast an event with standard format."""
        message = {
            "type": event_type,
            "data": data,
        }
        await self.broadcast(message)

    def get_connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)


class WebSocketEventBridge:
    """Bridges event bus events to WebSocket connections."""

    def __init__(self, connection_manager: WebSocketConnectionManager, event_bus):
        self.connection_manager = connection_manager
        self.event_bus = event_bus
        self.subscriptions = {}

    async def start(self):
        """Subscribe to event bus events and forward to WebSocket."""
        event_types = [
            "market_data_updated",
            "volume_spike_detected",
            "economic_event_triggered",
            "alert_generated",
            "decision_generated",
            "risk_alert_triggered",
            "data_quality_degraded",
            "feed_divergence_detected",
        ]

        for event_type in event_types:
            handler = self._create_handler(event_type)
            self.event_bus.subscribe(event_type, handler)
            logger.info(f"Subscribed to event bus: {event_type}")

    def _create_handler(self, event_type: str):
        """Create a handler that forwards event bus events to WebSocket."""
        async def handler(event):
            await self.connection_manager.broadcast_event(event_type, {
                "event_id": getattr(event, "event_id", None),
                "symbol": getattr(event, "symbol", None),
                "details": str(event),
                "severity": getattr(event, "severity", "info"),
            })
        return handler

    async def send_heartbeat(self):
        """Send periodic heartbeat to keep connections alive."""
        while True:
            await asyncio.sleep(30)
            await self.connection_manager.broadcast_event("heartbeat", {
                "status": "alive",
                "connections": self.connection_manager.get_connection_count(),
            })
