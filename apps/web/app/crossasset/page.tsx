"use client";

import { usePolling } from "@/lib/usePolling";

type Scan = {
  readings: {
    pair: string;
    correlation_now: number | null;
    correlation_baseline: number | null;
    state: string;
    detail: string;
  }[];
  risk_regime: { risk_mode: string; score: number; detail: string };
  anomaly_count: number;
};

const STATE_CLS: Record<string, string> = {
  NORMAL_RELATIONSHIP: "",
  DIVERGENCE: "text-[#f59e0b]",
  REGIME_CHANGE: "down",
  ABNORMAL_RELATIONSHIP: "down",
  INSUFFICIENT_DATA: "text-[#71809a]",
};

export default function CrossAssetDashboard() {
  const scan = usePolling<Scan>("/api/v1/cross_asset/scan", 60000);

  return (
    <div className="flex flex-col gap-4">
      <div className="panel">
        <div className="panel-title flex justify-between">
          <span>CROSS-ASSET MATRIX</span>
          <span className={`normal-case tracking-normal ${scan.data && scan.data.anomaly_count > 0 ? "text-[#f59e0b]" : ""}`}>
            {scan.data ? `${scan.data.anomaly_count} anomaly(ies)` : ""}
          </span>
        </div>
        <table className="w-full text-[12px]">
          <thead className="text-[#71809a] border-b border-[#1e2936]">
            <tr>
              <th className="text-left px-3 py-2">PAIR</th>
              <th className="text-right px-3 py-2">ρ NOW</th>
              <th className="text-right px-3 py-2">ρ BASE</th>
              <th className="text-left px-3 py-2">STATE</th>
              <th className="text-left px-3 py-2">DETAIL</th>
            </tr>
          </thead>
          <tbody>
            {(scan.data?.readings ?? []).map((r) => (
              <tr key={r.pair} className="border-b border-[#141c28] hover:bg-[#141c28]">
                <td className="px-3 py-1.5 font-bold">{r.pair}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">
                  {r.correlation_now != null ? r.correlation_now.toFixed(2) : "—"}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums text-[#71809a]">
                  {r.correlation_baseline != null ? r.correlation_baseline.toFixed(2) : "—"}
                </td>
                <td className={`px-3 py-1.5 ${STATE_CLS[r.state] ?? ""}`}>{r.state}</td>
                <td className="px-3 py-1.5 text-[#71809a]">{r.detail}</td>
              </tr>
            ))}
            {(scan.data?.readings ?? []).length === 0 && (
              <tr><td colSpan={5} className="px-3 py-3 text-[#71809a]">
                NO DATA AVAILABLE — need candles in DB for pair symbols
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-[10px] text-[#71809a]">
        States per thresholds: |Δρ|&gt;0.35 DIVERGENCE, &gt;0.60 REGIME CHANGE, sign
        contradiction ABNORMAL. DERIVED data — not a trading signal.
      </p>
    </div>
  );
}
