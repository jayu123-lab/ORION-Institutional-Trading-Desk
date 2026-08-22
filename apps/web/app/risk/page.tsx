"use client";

import { usePolling } from "@/lib/usePolling";

type Position = { id: number; symbol: string; net_qty: number; avg_entry: number };

const LIMITS = {
  per_trade_pct: 1.0,
  daily_risk_pct: 3.0,
  weekly_risk_pct: 6.0,
  drawdown_halt_pct: 10.0,
  exposure_total_cap: 3.0,
  single_asset_cap: 1.5,
};

export default function RiskPage() {
  const positions = usePolling<Position[]>("/api/v1/trades/positions", 10000);
  const equity = 100000; // ORION_STARTING_EQUITY default

  const grossNotional = (positions.data ?? []).reduce(
    (acc, p) => acc + Math.abs(p.net_qty * p.avg_entry),
    0
  );
  const exposureX = grossNotional / equity;

  const bars: [string, number, number, "up" | "down"][] = [
    ["Exposición bruta / equity", exposureX, LIMITS.exposure_total_cap, "up"],
    [
      "Exposición por activo máx.",
      (positions.data ?? []).reduce((m, p) => Math.max(m, Math.abs(p.net_qty * p.avg_entry) / equity), 0),
      LIMITS.single_asset_cap,
      "up",
    ],
    ["Riesgo diario usado", 0, LIMITS.daily_risk_pct, "down"],
    ["Drawdown actual", 0, LIMITS.drawdown_halt_pct, "down"],
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="panel">
        <div className="panel-title">Risk Dashboard · límites de mesa</div>
        <div className="p-4 space-y-4">
          {bars.map(([label, used, cap, tone]) => {
            const pct = cap > 0 ? Math.min(100, (used / cap) * 100) : 0;
            return (
              <div key={label}>
                <div className="flex justify-between text-[11px] mb-1">
                  <span>{label}</span>
                  <span className={tone === "up" ? "up" : "down"}>
                    {used.toFixed(2)} / {cap}
                  </span>
                </div>
                <div className="h-2 bg-[#141c28] rounded overflow-hidden border border-[#1e2936]">
                  <div
                    className={`h-full ${pct > 80 ? "bg-[#ef4444]" : pct > 50 ? "bg-[#f59e0b]" : "bg-[#22c55e]"}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="panel text-[12px]">
        <div className="panel-title">Reglas del Veto (Risk Manager)</div>
        <ul className="p-4 space-y-1 list-disc list-inside text-[#71809a] leading-relaxed">
          <li>Datos STALE/DISCONNECTED → REJECTED automático.</li>
          <li>R:R &lt; mínimo configurado → REJECTED.</li>
          <li>Límite diario/semanal o caps de exposición → REDUCE_SIZE si el fit ≥ 0.25.</li>
          <li>Evento HIGH impacto en ventana → WAIT hasta pasar la ventana.</li>
          <li>Drawdown ≥ halt → mesa cerrada (REJECTED total).</li>
        </ul>
        <p className="px-4 pb-4 text-[10px] text-[#71809a]">
          Nota: riesgo diario/drawdown se calculan server-side al ejecutar risk-review;
          aquí se muestran como referencia estática de límites.
        </p>
      </div>
    </div>
  );
}
