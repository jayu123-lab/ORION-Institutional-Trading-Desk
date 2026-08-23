"use client";

import { usePolling } from "@/lib/usePolling";
import { apiPost } from "@/lib/api";

type QuoteRow = {
  symbol: string;
  price?: number | null;
  provider?: string;
  proxy_of?: string | null;
  status: string;
  ts?: string;
};

type Debate = {
  id: number;
  ts: string | null;
  stance: string | null;
  confidence: string | null;
  summary: string;
};

const GOLD_SYMBOLS = ["XAUUSD", "GC", "MGC", "DXY", "US10Y", "US02Y"];

export default function GoldDashboard() {
  const quotes = usePolling<QuoteRow[]>("/api/v1/market/quotes", 15000);
  const debates = usePolling<Debate[]>("/api/v1/desk/XAUUSD/debates?limit=3", 60000);

  const rows = (quotes.data ?? []).filter((q) => GOLD_SYMBOLS.includes(q.symbol));

  async function convene() {
    try {
      await apiPost("/api/v1/desk/XAUUSD/convene", {});
      setTimeout(() => void debates.refresh(), 500);
    } catch {
      /* endpoint error surfaces on next refresh */
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="panel">
        <div className="panel-title">GOLD COMPLEX · XAUUSD / GC / MGC + DRIVERS</div>
        {quotes.error ? (
          <p className="p-4 text-[#ef4444]">API OFFLINE — {quotes.error}</p>
        ) : (
        <table className="w-full text-[12px]">
          <thead className="text-[#71809a] border-b border-[#1e2936]">
            <tr>
              <th className="text-left px-3 py-2">SYMBOL</th>
              <th className="text-right px-3 py-2">LAST</th>
              <th className="text-left px-3 py-2">PROVIDER</th>
              <th className="text-left px-3 py-2">STATUS</th>
              <th className="text-left px-3 py-2">UPDATED</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((q) => (
              <tr key={q.symbol} className="border-b border-[#141c28] hover:bg-[#141c28]">
                <td className="px-3 py-1.5 font-bold">{q.symbol}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{q.price ?? "—"}</td>
                <td className="px-3 py-1.5 text-[#71809a]">
                  {q.provider
                    ? q.proxy_of
                      ? `${q.provider} · proxy ${q.proxy_of}`
                      : q.provider
                    : "NOT AVAILABLE"}
                </td>
                <td className={`px-3 py-1.5 status-${q.status.toLowerCase()}`}>
                  {q.status === "NO_DATA" ? "NO DATA" : q.status}
                </td>
                <td className="px-3 py-1.5 text-[#71809a]">{q.ts?.slice(11, 19) ?? "—"}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-3 text-[#71809a]">WAITING FOR FIRST DATA…</td></tr>
            )}
          </tbody>
        </table>
        )}
      </div>

      <div className="panel">
        <div className="panel-title flex justify-between items-center">
          <span>DESK DEBATE · XAUUSD</span>
          <button
            onClick={() => void convene()}
            className="normal-case tracking-normal text-[10px] border border-[#1e2936] rounded px-2 py-0.5 hover:border-[#38bdf8]"
          >
            ▶ CONVENE
          </button>
        </div>
        <div className="p-3 space-y-3">
          {(debates.data ?? []).map((d) => (
            <div key={d.id} className="border-l border-[#1e2936] pl-3">
              <p className="text-[11px]">
                <span className={d.stance?.includes("BULL") ? "up" : d.stance?.includes("BEAR") ? "down" : ""}>
                  {d.stance ?? "—"}
                </span>{" "}
                · confidence {d.confidence ?? "—"}{" "}
                <span className="text-[#71809a]">{d.ts?.slice(0, 19)}</span>
              </p>
              <p className="text-[12px] text-[#c9d4e3]/90 whitespace-pre-wrap mt-1">{d.summary}</p>
            </div>
          ))}
          {(debates.data ?? []).length === 0 && (
            <p className="text-[#71809a] text-[12px]">
              NO DATA AVAILABLE — run CONVENE to generate the first debate.
            </p>
          )}
        </div>
      </div>

      <p className="text-[10px] text-[#71809a]">
        Labels are internal model tags, not financial advice. COT positioning available at
        POSITIONING tab.
      </p>
    </div>
  );
}
