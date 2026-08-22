"use client";

import { usePolling } from "@/lib/usePolling";

type Idea = {
  id: number;
  symbol: string;
  side: string;
  state: string;
  entry: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  author: string | null;
  created_at: string | null;
};

type Order = {
  id: number;
  client_order_id: string;
  symbol: string;
  side: string;
  order_type: string;
  quantity: number;
  limit_price: number | null;
  state: string;
};

type Position = {
  id: number;
  symbol: string;
  net_qty: number;
  avg_entry: number;
  realized_pnl: number;
};

function StateTag({ s }: { s: string }) {
  const color =
    s.startsWith("APPROVED") || s === "FILLED"
      ? "up"
      : s.includes("REJECT")
        ? "down"
        : s.includes("WAIT") || s.includes("PENDING") || s.includes("AWAITING")
          ? "text-[#f59e0b]"
          : "";
  return <span className={color}>{s}</span>;
}

export default function TradesPage() {
  const ideas = usePolling<Idea[]>("/api/v1/trades/ideas", 6000);
  const orders = usePolling<Order[]>("/api/v1/trades/orders", 6000);
  const positions = usePolling<Position[]>("/api/v1/trades/positions", 6000);

  return (
    <div className="grid grid-cols-2 gap-4">
      <div className="panel">
        <div className="panel-title">Trade Ideas</div>
        {ideas.error ? (
          <p className="p-4 text-[#ef4444]">API offline</p>
        ) : (ideas.data ?? []).length === 0 ? (
          <p className="p-4 text-[#71809a]">Sin ideas registradas.</p>
        ) : (
          <table className="w-full text-[12px]">
            <thead className="text-[#71809a] border-b border-[#1e2936]">
              <tr>
                <th className="text-left px-3 py-2">#</th>
                <th className="text-left px-3 py-2">SYMBOL</th>
                <th className="text-left px-3 py-2">SIDE</th>
                <th className="text-right px-3 py-2">ENTRY</th>
                <th className="text-right px-3 py-2">SL</th>
                <th className="text-right px-3 py-2">TP</th>
                <th className="text-left px-3 py-2">ESTADO</th>
              </tr>
            </thead>
            <tbody>
              {(ideas.data ?? []).map((i) => (
                <tr key={i.id} className="border-b border-[#141c28]">
                  <td className="px-3 py-1.5 text-[#71809a]">{i.id}</td>
                  <td className="px-3 py-1.5 font-bold">{i.symbol}</td>
                  <td className={`px-3 py-1.5 ${i.side === "BUY" ? "up" : "down"}`}>{i.side}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{i.entry ?? "—"}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums down">{i.stop_loss ?? "—"}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums up">{i.take_profit ?? "—"}</td>
                  <td className="px-3 py-1.5"><StateTag s={i.state} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <div className="panel-title">Orders · Paper Engine</div>
        {orders.error ? (
          <p className="p-4 text-[#ef4444]">API offline</p>
        ) : (orders.data ?? []).length === 0 ? (
          <p className="p-4 text-[#71809a]">Sin órdenes.</p>
        ) : (
          <table className="w-full text-[12px]">
            <thead className="text-[#71809a] border-b border-[#1e2936]">
              <tr>
                <th className="text-left px-3 py-2">CLIENT ID</th>
                <th className="text-left px-3 py-2">SYM</th>
                <th className="text-left px-3 py-2">SIDE</th>
                <th className="text-right px-3 py-2">QTY</th>
                <th className="text-left px-3 py-2">ESTADO</th>
              </tr>
            </thead>
            <tbody>
              {(orders.data ?? []).map((o) => (
                <tr key={o.id} className="border-b border-[#141c28]">
                  <td className="px-3 py-1.5 text-[10px] text-[#71809a]">{o.client_order_id.slice(0, 18)}…</td>
                  <td className="px-3 py-1.5">{o.symbol}</td>
                  <td className={`px-3 py-1.5 ${o.side === "BUY" ? "up" : "down"}`}>{o.side}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{o.quantity}</td>
                  <td className="px-3 py-1.5"><StateTag s={o.state} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel col-span-2">
        <div className="panel-title">Posiciones Abiertas (paper)</div>
        {(positions.data ?? []).length === 0 && !positions.error ? (
          <p className="p-4 text-[#71809a]">Flat — sin posiciones abiertas.</p>
        ) : (
          <table className="w-full text-[12px]">
            <thead className="text-[#71809a] border-b border-[#1e2936]">
              <tr>
                <th className="text-left px-3 py-2">SYMBOL</th>
                <th className="text-right px-3 py-2">NET QTY</th>
                <th className="text-right px-3 py-2">AVG ENTRY</th>
                <th className="text-right px-3 py-2">REALIZED P&L</th>
              </tr>
            </thead>
            <tbody>
              {(positions.data ?? []).map((p) => (
                <tr key={p.id} className="border-b border-[#141c28]">
                  <td className="px-3 py-1.5 font-bold">{p.symbol}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{p.net_qty}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{p.avg_entry}</td>
                  <td className={`px-3 py-1.5 text-right tabular-nums ${p.realized_pnl >= 0 ? "up" : "down"}`}>
                    {p.realized_pnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
