"use client";

import { usePolling } from "@/lib/usePolling";

type MacroRow = {
  id: number;
  event: string;
  region: string;
  scheduled_at: string;
  actual: string | null;
  consensus: string | null;
  previous: string | null;
  importance: string;
};

export default function MacroPage() {
  const { data, error, loading } = usePolling<MacroRow[]>("/api/v1/macro?limit=50", 30000);

  return (
    <div className="panel">
      <div className="panel-title">Macro Calendar · eventos</div>
      {error ? (
        <p className="p-4 text-[#ef4444]">API offline — {error}</p>
      ) : loading ? (
        <p className="p-4 text-[#71809a]">cargando…</p>
      ) : (data ?? []).length === 0 ? (
        <p className="p-4 text-[#71809a]">
          Calendario vacío. NO DATA AVAILABLE — la ingesta del calendario macro
          llega con los providers de Fase 2.
        </p>
      ) : (
        <table className="w-full text-[12px]">
          <thead className="text-[#71809a] border-b border-[#1e2936]">
            <tr>
              <th className="text-left px-3 py-2">FECHA (UTC)</th>
              <th className="text-left px-3 py-2">EVENTO</th>
              <th className="text-left px-3 py-2">REGIÓN</th>
              <th className="text-right px-3 py-2">ACTUAL</th>
              <th className="text-right px-3 py-2">CONSENSO</th>
              <th className="text-right px-3 py-2">PREVIO</th>
              <th className="text-left px-3 py-2">IMP.</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((m) => (
              <tr key={m.id} className="border-b border-[#141c28] hover:bg-[#141c28]">
                <td className="px-3 py-1.5 text-[#71809a]">{m.scheduled_at.slice(0, 16)}</td>
                <td className="px-3 py-1.5">{m.event}</td>
                <td className="px-3 py-1.5 text-[#71809a]">{m.region}</td>
                <td className="px-3 py-1.5 text-right tabular-nums up">{m.actual ?? "—"}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{m.consensus ?? "—"}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-[#71809a]">
                  {m.previous ?? "—"}
                </td>
                <td className={`px-3 py-1.5 ${m.importance === "HIGH" ? "text-[#ef4444]" : ""}`}>
                  {m.importance}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
