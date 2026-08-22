"use client";

import { usePolling } from "@/lib/usePolling";

type SystemStatus = {
  database: { status: string; engine: string };
  overall: string;
  feeds: { source: string; kind: string; status: string; last_update: string | null }[];
  uptime_seconds: number;
  live_mode: boolean;
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
          <p className={`text-lg font-bold ${data?.overall === "OPERATIONAL" ? "up" : "down"}`}>
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
          GET /health → verificación manual desde terminal:
          <br />
          <code className="text-[#22c55e]">curl http://127.0.0.1:8000/health</code>
        </p>
      </div>
    </div>
  );
}
