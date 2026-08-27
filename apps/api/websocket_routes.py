import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from apps.api.websocket_manager import WebSocketConnectionManager, WebSocketEventBridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])
connection_manager: WebSocketConnectionManager | None = None
event_bridge: WebSocketEventBridge | None = None


def init_websocket(manager: WebSocketConnectionManager, bridge: WebSocketEventBridge):
    """Initialize WebSocket connections with managers."""
    global connection_manager, event_bridge
    connection_manager = manager
    event_bridge = bridge


@router.websocket("/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket endpoint for real-time market and event streaming."""
    if connection_manager is None:
        await websocket.close(code=1011, reason="WebSocket manager not initialized")
        return

    await connection_manager.connect(websocket)
    try:
        # Send initial connection acknowledgment
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to ORION event stream",
            "connections": connection_manager.get_connection_count(),
        })

        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received from client: {data}")

            if data == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        await connection_manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await connection_manager.disconnect(websocket)


@router.websocket("/market/{symbol}")
async def websocket_market_data(websocket: WebSocket, symbol: str):
    """WebSocket endpoint for symbol-specific market data streaming."""
    if connection_manager is None:
        await websocket.close(code=1011, reason="WebSocket manager not initialized")
        return

    await connection_manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "subscribed",
            "symbol": symbol,
            "message": f"Subscribed to {symbol} data",
        })

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "symbol": symbol})

    except WebSocketDisconnect:
        await connection_manager.disconnect(websocket)
        logger.info(f"WebSocket client disconnected from {symbol}")
    except Exception as e:
        logger.error(f"WebSocket error for {symbol}: {e}")
        await connection_manager.disconnect(websocket)
