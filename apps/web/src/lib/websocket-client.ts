type EventHandler = (data: any) => void;
type StatusHandler = (status: "connected" | "disconnected" | "error") => void;

export interface WebSocketClientOptions {
  url?: string;
  reconnect?: boolean;
  reconnectInterval?: number;
  reconnectAttempts?: number;
  heartbeatInterval?: number;
}

export class OrionWebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private eventHandlers: Map<string, EventHandler[]> = new Map();
  private statusHandlers: StatusHandler[] = [];
  private reconnect: boolean;
  private reconnectInterval: number;
  private reconnectAttempts: number;
  private currentReconnectAttempt: number = 0;
  private heartbeatInterval: number;
  private heartbeatTimer: NodeJS.Timer | null = null;

  constructor(options: WebSocketClientOptions = {}) {
    this.url = options.url || this.getWebSocketUrl();
    this.reconnect = options.reconnect !== false;
    this.reconnectInterval = options.reconnectInterval || 3000;
    this.reconnectAttempts = options.reconnectAttempts || 5;
    this.heartbeatInterval = options.heartbeatInterval || 30000;
  }

  private getWebSocketUrl(): string {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    return `${protocol}//${host}/ws/events`;
  }

  public connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
          console.log("WebSocket connected");
          this.currentReconnectAttempt = 0;
          this.notifyStatus("connected");
          this.setupHeartbeat();
          resolve();
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        this.ws.onerror = (error) => {
          console.error("WebSocket error:", error);
          this.notifyStatus("error");
          reject(error);
        };

        this.ws.onclose = () => {
          console.log("WebSocket disconnected");
          this.notifyStatus("disconnected");
          this.clearHeartbeat();
          this.attemptReconnect();
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  private handleMessage(rawData: string): void {
    try {
      const message = JSON.parse(rawData);
      const { type, data, timestamp } = message;

      if (type === "heartbeat") {
        console.debug("Heartbeat received");
        return;
      }

      if (type === "connected" || type === "pong") {
        console.debug(`Server response: ${type}`);
        return;
      }

      this.emit(type, { ...data, timestamp });
    } catch (error) {
      console.error("Failed to parse WebSocket message:", error);
    }
  }

  private setupHeartbeat(): void {
    this.clearHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send("ping");
      }
    }, this.heartbeatInterval);
  }

  private clearHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private attemptReconnect(): void {
    if (!this.reconnect || this.currentReconnectAttempt >= this.reconnectAttempts) {
      console.log("Max reconnection attempts reached");
      return;
    }

    this.currentReconnectAttempt++;
    const delay = this.reconnectInterval * Math.pow(2, this.currentReconnectAttempt - 1);
    console.log(`Attempting reconnect (${this.currentReconnectAttempt}/${this.reconnectAttempts}) in ${delay}ms`);

    setTimeout(() => {
      this.connect().catch((error) => {
        console.error("Reconnection failed:", error);
      });
    }, delay);
  }

  public on(eventType: string, handler: EventHandler): () => void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, []);
    }
    this.eventHandlers.get(eventType)!.push(handler);

    return () => {
      const handlers = this.eventHandlers.get(eventType);
      if (handlers) {
        handlers.splice(handlers.indexOf(handler), 1);
      }
    };
  }

  public onStatus(handler: StatusHandler): () => void {
    this.statusHandlers.push(handler);
    return () => {
      this.statusHandlers.splice(this.statusHandlers.indexOf(handler), 1);
    };
  }

  private emit(eventType: string, data: any): void {
    const handlers = this.eventHandlers.get(eventType);
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(data);
        } catch (error) {
          console.error(`Error in event handler for ${eventType}:`, error);
        }
      });
    }
  }

  private notifyStatus(status: "connected" | "disconnected" | "error"): void {
    this.statusHandlers.forEach((handler) => {
      try {
        handler(status);
      } catch (error) {
        console.error("Error in status handler:", error);
      }
    });
  }

  public send(message: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(message);
    } else {
      console.warn("WebSocket is not connected");
    }
  }

  public disconnect(): void {
    this.reconnect = false;
    this.clearHeartbeat();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  public isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  public getStatus(): "connected" | "disconnected" | "connecting" {
    if (!this.ws) return "disconnected";
    if (this.ws.readyState === WebSocket.OPEN) return "connected";
    if (this.ws.readyState === WebSocket.CONNECTING) return "connecting";
    return "disconnected";
  }
}

// Export singleton instance
export const orionWebSocket = new OrionWebSocketClient();
