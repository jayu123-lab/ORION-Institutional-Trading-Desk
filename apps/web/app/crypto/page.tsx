"use client";

import { usePolling } from "@/lib/usePolling";

type QuoteRow = {
  symbol: string;
  price?: number | null;
  provider?: string;
  status: string;
};

const CRYPTO = ["BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD"];

export default function CryptoDashboard() {
  const quotes = usePolling<QuoteRow[]>("/api/v1/market/quotes", 10000);
  const rows = (quotes.data ?? []).filter((q) => CRYPTO.includes(q.symbol));
  const rtdsRows = rows.filter((q) => q.provider === "polymarket-rtds");

  return (
    <div className="flex flex-col gap-4">
      <div className="panel">
        <div className="panel-title">CRYPTO · MAJORS + XRP</div>
        <table className="w-full text-[12px]">
          <thead className="text-[#71809a] border-b border-[#1e2936]">
            <tr>
              <th className="text-left px-3 py-2">SYMBOL</th>
              <th className="text-right px-3 py-2">LAST</th>
              <th className="text-left px-3 py-2">PROVIDER</th>
              <th className="text-left px-3 py-2">STATUS</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((q) => (
              <tr key={q.symbol} className="border-b border-[#141c28] hover:bg-[#141c28]">
                <td className="px-3 py-1.5 font-bold">{q.symbol}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{q.price ?? "—"}</td>
                <td className="px-3 py-1.5 text-[#71809a]">{q.provider ?? "—"}</td>
                <td className={`px-3 py-1.5 status-${q.status.toLowerCase()}`}>{q.status}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-3 text-[#71809a]">NO DATA AVAILABLE</td></tr>
            )}
          </tbody>
        </table>
        {rtdsRows.length > 0 && (
          <p className="px-3 py-2 text-[10px] up">RTDS institutional-grade stream active for {rtdsRows.length} symbol(s)</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="panel">
          <div className="panel-title">XRP PANEL</div>
          <div className="p-4 text-[12px] space-y-1">
            <p>PRICE: {rows.find((q) => q.symbol === "XRPUSD")?.price ?? "—"}</p>
            <p className="text-[#71809a]">CORRELATION vs BTC: see CROSS-ASSET tab</p>
          </div>
        </div>
        <div className="panel">
          <div className="panel-title">DERIVATIVES DATA</div>
          <div className="p-4 text-[12px] space-y-1 text-[#71809a]">
            <p>OPEN INTEREST: NOT AVAILABLE — no verified feed connected</p>
            <p>FUNDING RATE: NOT AVAILABLE — no verified feed connected</p>
            <p>LIQUIDATIONS: NOT AVAILABLE — no verified feed connected</p>
          </div>
        </div>
      </div>

      <p className="text-[10px] text-[#71809a]">
        Per desk rules: panels show NOT AVAILABLE rather than estimated values until a real
        source is wired.
      </p>
    </div>
  );
}
