"use client";

import { usePolling } from "@/lib/usePolling";

type DeskAgent = {
  agent_id: string;
  name: string;
  role: string;
  capabilities: string[];
  asset_classes: string[];
  dependencies: string[];
  status: string;
  health: string;
  last_run: string | null;
  last_error: string | null;
};

function healthColor(h: string): string {
  if (h === "HEALTHY") return "status-live";
  if (h === "STALE") return "text-[#f59e0b]";
  if (h === "NEVER_RUN") return "text-[#71809a]";
  return "text-[#71809a]";
}

function statusColor(s: string): string {
  if (s === "READY") return "text-[#22c55e]";
  if (s === "DEGRADED") return "text-[#f59e0b]";
  return "text-[#ef4444]";
}

export default function AgentsPage() {
  const { data, error, loading } = usePolling<DeskAgent[]>("/api/v1/agents", 15000);

  return (
    <div className="panel">
      <div className="panel-title">ORION DESK · AGENT REGISTRY</div>
      <p className="px-3 pb-2 text-[10px] text-[#71809a]">
        Status is evidence-based: HEALTHY requires a real run in the last 24h. Agents that never
        executed honestly report NEVER_RUN.
      </p>
      {error ? (
        <p className="p-4 text-[#ef4444]">API offline — {error}</p>
      ) : loading ? (
        <p className="p-4 text-[#71809a]">cargando…</p>
      ) : (
        <table className="w-full text-[12px]">
          <thead className="text-[#71809a] border-b border-[#1e2936]">
            <tr>
              <th className="text-left px-3 py-2">AGENT</th>
              <th className="text-left px-3 py-2">ROLE</th>
              <th className="text-left px-3 py-2">STATUS</th>
              <th className="text-left px-3 py-2">HEALTH</th>
              <th className="text-left px-3 py-2">LAST RUN (UTC)</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((a) => (
              <tr key={a.agent_id} className="border-b border-[#141c28] hover:bg-[#141c28]">
                <td className="px-3 py-1.5 font-bold">{a.name}</td>
                <td className="px-3 py-1.5 text-[#71809a]">
                  {a.role}
                  {a.capabilities.length > 0 && (
                    <span className="block text-[9px] text-[#526078]">
                      {a.capabilities.slice(0, 4).join(" · ")}
                    </span>
                  )}
                </td>
                <td className={`px-3 py-1.5 ${statusColor(a.status)}`}>{a.status}</td>
                <td className={`px-3 py-1.5 ${healthColor(a.health)}`}>
                  {a.health}
                  {a.last_error && (
                    <span className="block text-[9px]" title={a.last_error}>
                      ⚠ last error
                    </span>
                  )}
                </td>
                <td className="px-3 py-1.5 text-[#71809a] text-[10px]">
                  {a.last_run ? a.last_run.slice(0, 19).replace("T", " ") : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
