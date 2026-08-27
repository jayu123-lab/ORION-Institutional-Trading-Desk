# WebSocket Real-Time Integration

ORION now includes full WebSocket support for real-time market data, alerts, and decision streaming to connected dashboard clients.

## Features

- **Live Event Streaming**: All market events broadcast to connected clients in real-time
- **Automatic Reconnection**: Exponential backoff reconnection with configurable attempts
- **Heartbeat Monitoring**: Keeps connections alive with periodic ping/pong
- **Event Types**: 8+ event types including market updates, volume spikes, alerts, and decisions
- **Connection Management**: Handles multiple simultaneous connections efficiently

## Server-Side Architecture

### WebSocket Manager (`apps/api/websocket_manager.py`)

**WebSocketConnectionManager**
- Manages active WebSocket connections
- Thread-safe connection operations using async locks
- Broadcasts messages to all connected clients
- Automatic cleanup of failed connections

```python
from apps.api.websocket_manager import WebSocketConnectionManager

manager = WebSocketConnectionManager()
await manager.connect(websocket)
await manager.broadcast({"type": "event", "data": {...}})
await manager.disconnect(websocket)
```

**WebSocketEventBridge**
- Bridges ORION event bus to WebSocket clients
- Subscribes to 8+ event types
- Sends heartbeat every 30 seconds
- Graceful error handling

```python
from apps.api.websocket_manager import WebSocketEventBridge

bridge = WebSocketEventBridge(manager, event_bus)
await bridge.start()  # Subscribe to events
await bridge.send_heartbeat()  # Periodic heartbeat
```

### Supported Event Types

The bridge subscribes to these events from the ORION event bus:

1. **market_data_updated** - Real-time price and volume data
2. **volume_spike_detected** - Abnormal volume detected on a symbol
3. **economic_event_triggered** - Scheduled economic event occurs
4. **alert_generated** - General alert from monitoring systems
5. **decision_generated** - New trade decision from autonomous layer
6. **risk_alert_triggered** - Risk manager generates warning
7. **data_quality_degraded** - Data quality issue detected
8. **feed_divergence_detected** - Market data divergence warning

### FastAPI Integration

The WebSocket routes are integrated into the FastAPI app at startup:

```python
# apps/api/main.py
ws_manager = WebSocketConnectionManager()
ws_bridge = WebSocketEventBridge(ws_manager, bus)
websocket_routes.init_websocket(ws_manager, ws_bridge)
await ws_bridge.start()
heartbeat_task = asyncio.create_task(ws_bridge.send_heartbeat())
```

## Client-Side Integration

### TypeScript Client (`apps/web/src/lib/websocket-client.ts`)

**OrionWebSocketClient** provides a high-level interface:

```typescript
import { orionWebSocket } from '@/lib/websocket-client';

// Connect to server
await orionWebSocket.connect();

// Listen for events
const unsubscribe = orionWebSocket.on('volume_spike_detected', (data) => {
  console.log('Volume spike on', data.symbol, data.details);
  // Update UI
});

// Monitor connection status
orionWebSocket.onStatus((status) => {
  console.log('Connection:', status); // 'connected' | 'disconnected' | 'error'
});

// Clean up
unsubscribe();
orionWebSocket.disconnect();
```

### Features

- **Auto-reconnect**: Exponential backoff (3s, 6s, 12s, 24s, 48s)
- **Type Safety**: Fully typed with TypeScript interfaces
- **Event Handlers**: Subscribe/unsubscribe from specific events
- **Status Monitoring**: Track connection state
- **Heartbeat**: Automatic ping every 30s (configurable)
- **Error Handling**: Graceful error propagation

### Configuration

```typescript
const client = new OrionWebSocketClient({
  url: 'ws://localhost:8000/ws/events',     // Custom URL
  reconnect: true,                           // Auto-reconnect
  reconnectInterval: 3000,                   // Initial delay (ms)
  reconnectAttempts: 5,                      // Max attempts
  heartbeatInterval: 30000,                  // Ping interval (ms)
});

await client.connect();
```

## API Endpoints

### `/ws/events` (Main Event Stream)
Broadcasts all ORION events to connected clients.

**Connection**:
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/events');
```

**Message Format**:
```json
{
  "type": "market_data_updated",
  "data": {
    "symbol": "BTC",
    "price": 95000.50,
    "volume": 1234.56
  },
  "timestamp": "2026-08-27T10:30:45.123Z"
}
```

### `/ws/market/{symbol}` (Symbol-Specific Stream)
Streams data only for a specific symbol.

**Connection**:
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/market/BTC');
```

**Usage**:
```javascript
ws.onopen = () => {
  console.log('Subscribed to BTC data');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log(`${message.symbol} update:`, message.data);
};
```

## Example: Real-Time Dashboard Update

```typescript
// src/hooks/useOrionEvents.ts
import { useEffect, useState } from 'react';
import { orionWebSocket } from '@/lib/websocket-client';

export function useOrionEvents() {
  const [status, setStatus] = useState('disconnected');
  const [events, setEvents] = useState([]);

  useEffect(() => {
    orionWebSocket.connect().catch(console.error);

    // Monitor events
    const eventTypes = [
      'market_data_updated',
      'volume_spike_detected',
      'decision_generated',
      'risk_alert_triggered',
    ];

    const unsubscribers = eventTypes.map((type) =>
      orionWebSocket.on(type, (data) => {
        setEvents((prev) => [{ type, data, timestamp: new Date() }, ...prev].slice(0, 50));
      })
    );

    // Monitor status
    const unsubscribeStatus = orionWebSocket.onStatus(setStatus);

    return () => {
      unsubscribers.forEach((fn) => fn());
      unsubscribeStatus();
      orionWebSocket.disconnect();
    };
  }, []);

  return { status, events };
}

// src/components/EventFeed.tsx
export function EventFeed() {
  const { status, events } = useOrionEvents();

  return (
    <div className="space-y-2">
      <div className={`status-badge ${status}`}>{status.toUpperCase()}</div>
      {events.map((event, i) => (
        <div key={i} className="event-item">
          <span className="type">{event.type}</span>
          <span className="time">{event.timestamp.toLocaleTimeString()}</span>
          <pre>{JSON.stringify(event.data, null, 2)}</pre>
        </div>
      ))}
    </div>
  );
}
```

## Monitoring & Debugging

### Server-Side Logs

```
INFO: WebSocket connected. Total connections: 1
INFO: Subscribed to event bus: market_data_updated
INFO: WebSocket client disconnected. Total connections: 0
ERROR: Error sending WebSocket message: Connection closed
```

### Client-Side Logs

```
WebSocket connected
Heartbeat received
WebSocket disconnected
Attempting reconnect (1/5) in 3000ms
```

### Health Check

```bash
curl http://localhost:8000/health
{
  "status": "ok",
  "service": "orion-api",
  "version": "0.1.0"
}
```

## Performance Considerations

- **Connection Limit**: Configure your server's max concurrent connections
- **Message Rate**: With multiple events per symbol, plan for 10-100+ messages/second
- **Bandwidth**: Each event ~200-500 bytes; estimate 2-50 Mbps for 100 concurrent clients
- **CPU**: Event bridge processing is minimal; bottleneck is usually network I/O

## Testing

Run the WebSocket test suite:

```bash
python -m pytest tests/test_websocket_manager.py -v
```

Tests cover:
- Connection lifecycle (connect/disconnect)
- Message broadcasting
- Event handling
- Failed client cleanup
- Heartbeat functionality

## Future Enhancements

- [ ] Message compression (gzip)
- [ ] Partial subscriptions (filter events by type)
- [ ] Event queue with persistence (Redis)
- [ ] Rate limiting per connection
- [ ] Client-side event buffering
- [ ] Metrics/monitoring dashboard
- [ ] TLS/WSS support

## Troubleshooting

**"WebSocket connection failed"**
- Check server is running: `curl http://localhost:8000/health`
- Verify WebSocket endpoint: `ws://localhost:8000/ws/events`
- Check firewall/proxy settings

**"Messages not received after connect"**
- Ensure event bus is running: check logs for "bus.start()"
- Verify events are being generated (check market data service)
- Check browser console for JavaScript errors

**"Connection keeps reconnecting"**
- Check server logs for errors
- Increase `reconnectAttempts` if temporary outages expected
- Monitor server resource usage (CPU, memory, connections)

---

**More Info**: See [DASHBOARD_ACCESS.md](DASHBOARD_ACCESS.md) for complete dashboard setup instructions.
