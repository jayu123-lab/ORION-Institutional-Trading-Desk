"use client";

import { usePolling } from "@/lib/usePolling";

type SystemStatus = {
  database: { status: string; engine: string };
  overall: string;
  feeds: { source: string; kind: string; status: string; last_update: string | null }[];
  services?: {
    service: string;
    state: string;
    detail: string;
  }[];
  event_bus?: string;
  uptime_seconds: number;
  live_mode: boolean;
};

const STATE_CLS: Record<string, string> = {
  HEALTHY: "up",
  OPERATIONAL: "up",
  CONNECTED: "up",
  IDLE: "text-[#71809a]",
  NOT_CONFIGURED: "text-[#71809a]",
  DEGRADED: "text-[#f59e0b]",
  STALE: "text-[#f59e0b]",
  FAILED: "down",
  DISCONNECTED: "down",
};

function fmtUptime(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h ${m}m`;
}

export default function StatusPage() {
  const { data, error, loading } = usePolling<SystemStatus>("/api/v1/system/status", 5000);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-4 gap-4">
        <div className="panel p-4">
          <p className="text-[10px] text-[#71809a] uppercase">Overall</p>
          <p className={`text-lg font-bold ${data?.overall === "OPERATIONAL" ? "up" : data?.overall === "DEGRADED" ? "text-[#f59e0b]" : "down"}`}>
            {loading ? "…" : (data?.overall ?? "OFFLINE")}
          </p>
        </div>
        <div className="panel p-4">
          <p className="text-[10px] text-[#71809a] uppercase">Database</p>
          <p className={`text-lg font-bold ${data?.database.status === "CONNECTED" ? "up" : "down"}`}>
            {data?.database.status ?? "—"}
          </p>
          <p className="text-[10px] text-[#71809a]">{data?.database.engine ?? ""}</p>
        </div>
        <div className="panel p-4">
          <p className="text-[10px] text-[#71809a] uppercase">Uptime</p>
          <p className="text-lg font-bold">{data ? fmtUptime(data.uptime_seconds) : "—"}</p>
        </div>
        <div className="panel p-4">
          <p className="text-[10px] text-[#71809a] uppercase">Live Mode</p>
          <p className={`text-lg font-bold ${data?.live_mode ? "down" : "up"}`}>
            {data?.live_mode ? "ENABLED ⚠" : "DISABLED"}
          </p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Services Health · HEALTHY / DEGRADED / STALE / FAILED</div>
        <table className="w-full text-[12px]">
          <thead className="text-[#71809a] border-b border-[#1e2936]">
            <tr>
              <th className="text-left px-3 py-2">SERVICE</th>
              <th className="text-left px-3 py-2">STATE</th>
              <th className="text-left px-3 py-2">DETAIL</th>
            </tr>
          </thead>
          <tbody>
            {(data?.services ?? []).map((s) => (
              <tr key={s.service} className="border-b border-[#141c28] hover:bg-[#141c28]">
                <td className="px-3 py-1.5 font-bold">{s.service}</td>
                <td className={`px-3 py-1.5 ${STATE_CLS[s.state] ?? ""}`}>{s.state}</td>
                <td className="px-3 py-1.5 text-[#71809a]">{s.detail}</td>
              </tr>
            ))}
            {(data?.services ?? []).length === 0 && (
              <tr><td colSpan={3} className="px-3 py-3 text-[#71809a]">
                NO DATA AVAILABLE (API anterior a P15 — reiniciar)
              </td></tr>
            )}
          </tbody>
        </table>
        {data?.event_bus && (
          <p className="px-3 py-2 text-[10px] text-[#71809a]">EVENT BUS: {data.event_bus}</p>
        )}
      </div>

      <div className="panel">
        <div className="panel-title">Feeds · Market Data Sources</div>
        {error ? (
          <p className="p-4 text-[#ef4444]">API offline — {error}</p>
        ) : (
          <table className="w-full text-[12px]">
            <thead className="text-[#71809a] border-b border-[#1e2936]">
              <tr>
                <th className="text-left px-3 py-2">SOURCE</th>
                <th className="text-left px-3 py-2">KIND</th>
                <th className="text-left px-3 py-2">STATUS</th>
                <th className="text-left px-3 py-2">LAST UPDATE</th>
              </tr>
            </thead>
            <tbody>
              {(data?.feeds ?? []).map((f) => (
                <tr key={f.source} className="border-b border-[#141c28] hover:bg-[#141c28]">
                  <td className="px-3 py-1.5 font-bold">{f.source}</td>
                  <td className="px-3 py-1.5 text-[#71809a]">{f.kind}</td>
                  <td className={`px-3 py-1.5 status-${f.status.toLowerCase()}`}>{f.status}</td>
                  <td className="px-3 py-1.5 text-[#71809a]">
                    {f.last_update?.slice(0, 19).replace("T", " ") ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <div className="panel-title">Health Probe</div>
        <p className="p-4 text-[11px] text-[#71809a] leading-relaxed">
          GET /api/v1/health (alias: /health) — verificación manual desde terminal:
          <br />
          <code className="text-[#22c55e]">curl http://127.0.0.1:8000/api/v1/health</code>
          <br />
          El estado de esta página se refresca cada 5s vía REST polling; el badge de
          transporte del Market Overview refleja WebSocket vs polling real.
        </p>
      </div>
    </div>
  );
}
