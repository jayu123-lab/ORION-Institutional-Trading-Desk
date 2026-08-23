"use client";

import { usePolling } from "@/lib/usePolling";

type Idea = {
  id: number;
  asset: string;
  direction: string | null;
  state: string | null;
  entry: number | null;
  stop_loss: number | null;
  tp1: number | null;
  ts: string | null;
};

export default function BacktestDashboard() {
  const ideas = usePolling<Idea[]>("/api/v1/ideas", 60000);

  return (
    <div className="flex flex-col gap-4">
      <div className="panel">
        <div className="panel-title">BACKTEST ENGINE</div>
        <div className="p-4 text-[12px] space-y-1 text-[#71809a]">
          <p>
            STATUS: <span className="text-[#f59e0b]">NOT AVAILABLE — engine not yet implemented</span>
          </p>
          <p>
            Planned: walk-forward replay over stored candles with PaperTradingEngine fills
            (slippage + partials), RiskEngine gates and per-regime attribution.
          </p>
          <p>Until then, no equity curve or performance figures are shown — none exist.</p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">SIGNAL LOG (LIVE IDEAS — NOT A BACKTEST)</div>
        <table className="w-full text-[12px]">
          <thead className="text-[#71809a] border-b border-[#1e2936]">
            <tr>
              <th className="text-left px-3 py-2">#</th>
              <th className="text-left px-3 py-2">ASSET</th>
              <th className="text-left px-3 py-2">DIR</th>
              <th className="text-right px-3 py-2">ENTRY</th>
              <th className="text-left px-3 py-2">STATE</th>
              <th className="text-left px-3 py-2">CREATED</th>
            </tr>
          </thead>
          <tbody>
            {(ideas.data ?? []).slice(0, 20).map((i) => (
              <tr key={i.id} className="border-b border-[#141c28] hover:bg-[#141c28]">
                <td className="px-3 py-1.5 text-[#71809a]">{i.id}</td>
                <td className="px-3 py-1.5 font-bold">{i.asset}</td>
                <td className={`px-3 py-1.5 ${i.direction === "LONG" ? "up" : i.direction === "SHORT" ? "down" : ""}`}>
                  {i.direction ?? "—"}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums">{i.entry ?? "—"}</td>
                <td className="px-3 py-1.5">{i.state ?? "—"}</td>
                <td className="px-3 py-1.5 text-[#71809a]">{i.ts?.slice(0, 19) ?? "—"}</td>
              </tr>
            ))}
            {(ideas.data ?? []).length === 0 && (
              <tr><td colSpan={5} className="px-3 py-3 text-[#71809a]">NO DATA AVAILABLE</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-[10px] text-[#71809a]">
        Internal research tooling only — labels are model tags, never financial advice.
      </p>
    </div>
  );
}
