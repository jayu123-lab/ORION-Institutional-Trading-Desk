"use client";

import { useState } from "react";
import { usePolling } from "@/lib/usePolling";

type Metric = { name: string; value: string | number | null; availability: string; detail?: string };
type Report = {
  symbol: string;
  as_of: string | null;
  metrics: Metric[];
  overall_availability: string;
  notes: string[];
};

const SYMBOLS = ["XAUUSD", "XAGUSD", "BTCUSD", "XRPUSD"];

export default function PositioningDashboard() {
  const [symbol, setSymbol] = useState("XAUUSD");
  const report = usePolling<Report>(`/api/v1/positioning/${symbol}`, 300000);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2">
        {SYMBOLS.map((s) => (
          <button
            key={s}
            onClick={() => setSymbol(s)}
            className={`text-[11px] px-3 py-1 rounded border ${
              s === symbol
                ? "border-[#38bdf8] text-white"
                : "border-[#1e2936] text-[#71809a] hover:text-white"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      <div className="panel">
        <div className="panel-title flex justify-between">
          <span>INSTITUTIONAL POSITIONING · {symbol}</span>
          <span className="normal-case tracking-normal text-[10px]">
            {report.data?.overall_availability ?? "…"}
          </span>
        </div>
        <table className="w-full text-[12px]">
          <thead className="text-[#71809a] border-b border-[#1e2936]">
            <tr>
              <th className="text-left px-3 py-2">METRIC</th>
              <th className="text-right px-3 py-2">VALUE</th>
              <th className="text-left px-3 py-2">AVAILABILITY</th>
            </tr>
          </thead>
          <tbody>
            {(report.data?.metrics ?? []).map((m) => (
              <tr key={m.name} className="border-b border-[#141c28]">
                <td className="px-3 py-1.5 font-bold">{m.name}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{m.value ?? "—"}</td>
                <td className={`px-3 py-1.5 ${m.availability === "VERIFIED_DATA" ? "up" : "text-[#71809a]"}`}>
                  {m.availability}
                </td>
              </tr>
            ))}
            {(report.data?.metrics ?? []).length === 0 && (
              <tr><td colSpan={3} className="px-3 py-3 text-[#71809a]">NO DATA AVAILABLE</td></tr>
            )}
          </tbody>
        </table>
        {(report.data?.notes ?? []).map((n, i) => (
          <p key={i}>· {n}</p>
        ))}
      </div>

      <p className="text-[10px] text-[#71809a]">
        COT data VERIFIED from CFTC Socrata (disaggregated futures-only). Gamma exposure /
        options OI / ETF flows / CTA trend estimates: NOT AVAILABLE until a verified source is
        connected.
      </p>
    </div>
  );
}
