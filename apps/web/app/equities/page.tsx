"use client";

import { usePolling } from "@/lib/usePolling";

type QuoteRow = { symbol: string; price?: number | null; provider?: string; status: string };
type Scan = {
  readings: {
    pair: string;
    correlation_now: number | null;
    correlation_baseline: number | null;
    state: string;
    detail: string;
  }[];
  risk_regime: { risk_mode: string; score: number; detail: string };
};

const EQUITIES = ["SPX", "NDX", "DJI", "VIX"];

const STATE_CLS: Record<string, string> = {
  NORMAL_RELATIONSHIP: "",
  DIVERGENCE: "text-[#f59e0b]",
  REGIME_CHANGE: "down",
  ABNORMAL_RELATIONSHIP: "down",
  INSUFFICIENT_DATA: "text-[#71809a]",
};

export default function EquitiesDashboard() {
  const quotes = usePolling<QuoteRow[]>("/api/v1/market/quotes", 15000);
  const scan = usePolling<Scan>("/api/v1/cross_asset/scan", 60000);
  const rows = (quotes.data ?? []).filter((q) => EQUITIES.includes(q.symbol));
  const spxVix = (scan.data?.readings ?? []).find((r) => r.pair === "SPX_VIX");

  return (
    <div className="flex flex-col gap-4">
      <div className="panel">
        <div className="panel-title">EQUITIES + VOLATILITY</div>
        <table className="w-full text-[12px]">
          <thead className="text-[#71809a] border-b border-[#1e2936]">
            <tr>
              <th className="text-left px-3 py-2">SYMBOL</th>
              <th className="text-right px-3 py-2">LAST</th>
              <th className="text-left px-3 py-2">STATUS</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((q) => (
              <tr key={q.symbol} className="border-b border-[#141c28] hover:bg-[#141c28]">
                <td className="px-3 py-1.5 font-bold">{q.symbol}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{q.price ?? "—"}</td>
                <td className={`px-3 py-1.5 status-${q.status.toLowerCase()}`}>{q.status}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={3} className="px-3 py-3 text-[#71809a]">NO DATA AVAILABLE</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <div className="panel-title">RISK REGIME · SPX / VIX / BTC</div>
        <div className="p-4 text-[12px] space-y-1">
          <p>
            MODE:{" "}
            <span className={scan.data?.risk_regime.risk_mode === "RISK_ON" ? "up" : scan.data?.risk_regime.risk_mode === "RISK_OFF" ? "down" : ""}>
              {scan.data?.risk_regime.risk_mode ?? "—"}
            </span>{" "}
            <span className="text-[#71809a]">score {scan.data?.risk_regime.score ?? "—"}</span>
          </p>
          <p className="text-[#71809a]">{scan.data?.risk_regime.detail ?? ""}</p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">SPX × VIX RELATION</div>
        <div className="p-4 text-[12px] space-y-1">
          {spxVix ? (
            <>
              <p>ρ now: {spxVix.correlation_now?.toFixed(2) ?? "—"} · baseline: {spxVix.correlation_baseline?.toFixed(2) ?? "—"}</p>
              <p className={STATE_CLS[spxVix.state] ?? ""}>{spxVix.state} — {spxVix.detail}</p>
            </>
          ) : (
            <p className="text-[#71809a]">NO DATA AVAILABLE</p>
          )}
        </div>
      </div>

      <p className="text-[10px] text-[#71809a]">
        Correlations DERIVED from stored candles — never presented as verified feed data.
      </p>
    </div>
  );
}
