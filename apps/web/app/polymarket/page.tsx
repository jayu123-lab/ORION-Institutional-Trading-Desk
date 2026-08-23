"use client";

import { usePolling } from "@/lib/usePolling";

type QuoteRow = { symbol: string; price?: number | null; provider?: string; status: string };

export default function PolymarketDashboard() {
  const quotes = usePolling<QuoteRow[]>("/api/v1/market/quotes", 10000);
  const rtds = (quotes.data ?? []).filter((q) => q.provider === "polymarket-rtds");
  const others = (quotes.data ?? []).filter((q) => q.provider && q.provider !== "polymarket-rtds" && q.price != null);

  return (
    <div className="flex flex-col gap-4">
      <div className="panel">
        <div className="panel-title flex justify-between">
          <span>POLYMARKET RTDS · CRYPTO STREAM</span>
          <span className={`normal-case tracking-normal ${rtds.length > 0 ? "up" : "down"}`}>
            {rtds.length > 0 ? "● LIVE" : "● NO DATA"}
          </span>
        </div>
        <table className="w-full text-[12px]">
          <thead className="text-[#71809a] border-b border-[#1e2936]">
            <tr>
              <th className="text-left px-3 py-2">SYMBOL</th>
              <th className="text-right px-3 py-2">LAST</th>
              <th className="text-left px-3 py-2">STATUS</th>
            </tr>
          </thead>
          <tbody>
            {rtds.map((q) => (
              <tr key={q.symbol} className="border-b border-[#141c28] hover:bg-[#141c28]">
                <td className="px-3 py-1.5 font-bold">{q.symbol}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{q.price ?? "—"}</td>
                <td className={`px-3 py-1.5 status-${q.status.toLowerCase()}`}>{q.status}</td>
              </tr>
            ))}
            {rtds.length === 0 && (
              <tr><td colSpan={3} className="px-3 py-3 text-[#71809a]">
                NO DATA AVAILABLE — start apps.monitor.polymarket_ws to populate
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="panel">
          <div className="panel-title">PREDICTION MARKET ODDS</div>
          <div className="p-4 text-[12px] text-[#71809a] space-y-1">
            <p>EVENT ODDS: NOT AVAILABLE</p>
            <p>Gamma markets API adapter not yet connected.</p>
          </div>
        </div>
        <div className="panel">
          <div className="panel-title">OTHER PROVIDERS (REFERENCE)</div>
          <div className="p-4 text-[12px] space-y-0.5 max-h-56 overflow-y-auto">
            {others.slice(0, 10).map((q) => (
              <p key={q.symbol} className="flex justify-between">
                <span>{q.symbol}</span>
                <span className="text-[#71809a] tabular-nums">{q.price}</span>
              </p>
            ))}
            {others.length === 0 && <p className="text-[#71809a]">NO DATA AVAILABLE</p>}
          </div>
        </div>
      </div>

      <p className="text-[10px] text-[#71809a]">
        RTDS crypto prices are the desk&apos;s only institutional-grade (PRIMARY/LIVE) feed.
      </p>
    </div>
  );
}
