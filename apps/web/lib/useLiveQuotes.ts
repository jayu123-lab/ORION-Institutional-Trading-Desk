"use client";

import { useEffect, useRef, useState } from "react";

export type LiveQuote = {
  symbol: string;
  price?: number | null;
  bid?: number | null;
  ask?: number | null;
  provider?: string;
  status: string;
  ts?: string;
};

export type Transport = "connecting" | "live" | "polling" | "offline";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const WS_URL = `${API_URL.replace(/^http/, "ws")}/ws/events`;

/**
 * Quotes via REST polling + PRICE_UPDATE push over /ws/events when available.
 * Transport shows what is feeding the UI right now.
 */
export function useLiveQuotes(pollMs = 10000) {
  const [quotes, setQuotes] = useState<LiveQuote[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [transport, setTransport] = useState<Transport>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function poll() {
    try {
      const res = await fetch(`${API_URL}/api/v1/market/quotes`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setQuotes(await res.json());
      setError(null);
      setTransport((t) => (t === "live" ? t : "polling"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setTransport("offline");
    }
  }

  function connectWs() {
    if (retryRef.current) clearTimeout(retryRef.current);
    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => setTransport("live");
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string);
          if (msg.topic !== "PRICE_UPDATE") return;
          const { symbol, price } = msg.payload ?? {};
          if (!symbol || typeof price !== "number") return;
          setQuotes((qs) =>
            qs.map((q) =>
              q.symbol === symbol ? { ...q, price, provider: "polymarket-rtds", status: "LIVE" } : q
            )
          );
        } catch {
          /* ignore malformed frame */
        }
      };
      ws.onclose = () => {
        setTransport((t) => (t === "live" ? "polling" : t));
        retryRef.current = setTimeout(connectWs, 3000);
      };
      ws.onerror = () => ws.close();
    } catch {
      retryRef.current = setTimeout(connectWs, 3000);
    }
  }

  useEffect(() => {
    void poll();
    const timer = setInterval(() => void poll(), pollMs);
    connectWs();
    return () => {
      clearInterval(timer);
      if (retryRef.current) clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollMs]);

  return { quotes, error, transport };
}
