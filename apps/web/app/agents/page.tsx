"use client";

import { usePolling } from "@/lib/usePolling";

type DeskAgent = {
  name: string;
  role: string;
  status: string;
  coverage?: string;
};

export default function AgentsPage() {
  const { data, error, loading } = usePolling<DeskAgent[]>("/api/v1/agents", 15000);

  return (
    <div className="panel">
      <div className="panel-title">Mesa · Agentes Registrados</div>
      {error ? (
        <p className="p-4 text-[#ef4444]">API offline — {error}</p>
      ) : loading ? (
        <p className="p-4 text-[#71809a]">cargando…</p>
      ) : (
        <table className="w-full text-[12px]">
          <thead className="text-[#71809a] border-b border-[#1e2936]">
            <tr>
              <th className="text-left px-3 py-2">AGENTE</th>
              <th className="text-left px-3 py-2">ROL</th>
              <th className="text-left px-3 py-2">ESTADO</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((a) => (
              <tr key={a.name} className="border-b border-[#141c28] hover:bg-[#141c28]">
                <td className="px-3 py-1.5 font-bold">@{a.name}</td>
                <td className="px-3 py-1.5 text-[#71809a]">{a.role}</td>
                <td className="px-3 py-1.5 status-live">{a.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
