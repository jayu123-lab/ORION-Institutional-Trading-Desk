"use client";

import { useLiveQuotes, type Transport } from "@/lib/useLiveQuotes";
import { usePolling } from "@/lib/usePolling";

type SessionClock = {
  utc: string;
  madrid: string;
  active_sessions: string[];
  next_event: { name: string; at_utc: string | null };
};

const TRANSPORT_LABEL: Record<Transport, { text: string; cls: string }> = {
  connecting: { text: "● CONNECTING", cls: "text-[#f59e0b]" },
  live: { text: "● LIVE WS", cls: "up" },
  polling: { text: "● POLLING", cls: "text-[#38bdf8]" },
  offline: { text: "● OFFLINE", cls: "down" },
};

export default function MarketOverview() {
  const { quotes, error, transport } = useLiveQuotes(10000);
  const sessions = usePolling<SessionClock>("/api/v1/market/sessions", 10000);
  const t = TRANSPORT_LABEL[transport];

  return (
    <div className="flex flex-col gap-4">
      <div className="panel">
        <div className="panel-title flex items-center justify-between">
          <span>Market Overview · Watchlist</span>
          <span className={`normal-case tracking-normal ${t.cls}`}>{t.text}</span>
        </div>
        {error ? (
          <p className="p-4 text-[#ef4444]">API offline — {error}</p>
        ) : (
          <table className="w-full text-[12px]">
            <thead className="text-[#71809a] border-b border-[#1e2936]">
              <tr>
                <th className="text-left px-3 py-2">SYMBOL</th>
                <th className="text-right px-3 py-2">LAST</th>
                <th className="text-right px-3 py-2">BID</th>
                <th className="text-right px-3 py-2">ASK</th>
                <th className="text-left px-3 py-2">PROVIDER</th>
                <th className="text-left px-3 py-2">STATUS</th>
              </tr>
            </thead>
            <tbody>
              {quotes.map((q) => (
                <tr key={q.symbol} className="border-b border-[#141c28] hover:bg-[#141c28]">
                  <td className="px-3 py-1.5 font-bold">{q.symbol}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {q.price != null ? q.price : "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-[#71809a]">
                    {q.bid ?? "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-[#71809a]">
                    {q.ask ?? "—"}
                  </td>
                  <td className="px-3 py-1.5 text-[#71809a]">{q.provider ?? "—"}</td>
                  <td className={`px-3 py-1.5 status-${q.status.toLowerCase()}`}>
                    {q.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="panel">
          <div className="panel-title">Desk Clock</div>
          <div className="p-4 space-y-1 text-[12px]">
            <p>UTC: {sessions.data?.utc.slice(11, 19) ?? "—"}</p>
            <p>MADRID: {sessions.data?.madrid.slice(11, 19) ?? "—"}</p>
            <p>
              ACTIVE:{" "}
              <span className="up">
                {(sessions.data?.active_sessions ?? []).join(" + ") || "CLOSED"}
              </span>
            </p>
          </div>
        </div>
        <div className="panel">
          <div className="panel-title">Next Event</div>
          <div className="p-4 text-[12px] space-y-1">
            <p>{sessions.data?.next_event.name ?? "—"}</p>
            <p className="text-[#71809a]">
              {sessions.data?.next_event.at_utc ?? ""}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
