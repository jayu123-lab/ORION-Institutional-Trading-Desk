"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

type State = "WAIT" | "OK" | "DEGRADED" | "FAIL";
type Check = { key: string; label: string; state: State; detail: string };
const CHECKS = [
  ["api", "API", "/health"], ["database", "DATABASE", "/api/v1/system/status"],
  ["market_feeds", "MARKET FEEDS", "/api/v1/system/status"], ["crypto", "CRYPTO", "/api/v1/command/ticker"],
  ["news", "NEWS", "/api/v1/news"], ["cftc", "CFTC", "/api/v1/positioning"],
  ["cio", "CIO", "/api/v1/cio/agents"], ["risk", "RISK", "/api/v1/trades/positions"],
] as const;

export default function StartPage() {
  const { t } = useLanguage();
  const [checks, setChecks] = useState<Check[]>([]);
  const [running, setRunning] = useState(false);

  async function runChecks() {
    setRunning(true);
    setChecks(CHECKS.map(([key, label]) => ({ key, label, state: "WAIT", detail: "…" })));
    for (const [key, label, endpoint] of CHECKS) {
      let state: State = "OK"; let detail = "READY";
      try {
        const response = await fetch(`${API_URL}${endpoint}`, { cache: "no-store" });
        if (!response.ok) { state = response.status >= 500 ? "FAIL" : "DEGRADED"; detail = `HTTP ${response.status}`; }
      } catch { state = "FAIL"; detail = "OFFLINE"; }
      setChecks((current) => current.map((item) => item.key === key ? { key, label, state, detail } : item));
    }
    setRunning(false);
  }

  useEffect(() => { void runChecks(); }, []);
  const ready = checks.length === CHECKS.length && checks.every((item) => item.state !== "WAIT");
  return <div className="mx-auto flex min-h-[calc(100vh-90px)] max-w-2xl items-center justify-center">
    <section className="panel w-full max-w-lg p-6">
      <div className="mb-6 flex items-center gap-4"><div className="text-3xl font-bold tracking-[0.25em] text-red-500">ORION</div><div><p className="text-xs tracking-widest text-[#c9d4e3]">{t("institutional_desk")}</p><p className="text-[10px] text-[#71809a]">ORION INITIALIZING</p></div></div>
      <h1 className="panel-title !px-0">{t("system_state")}</h1>
      <ul className="mt-3 space-y-2 text-xs">{checks.map((item) => <li key={item.key} className="flex justify-between border-b border-[#1e2936] pb-1.5"><span>{t(item.key)}</span><span className={item.state === "OK" ? "text-[#22c55e]" : item.state === "DEGRADED" ? "text-[#f59e0b]" : item.state === "FAIL" ? "text-[#ef4444]" : "text-[#71809a]"}>{item.detail}</span></li>)}</ul>
      <div className="mt-6 grid grid-cols-1 gap-2 sm:grid-cols-2"><Link href="/command" className={`rounded border px-3 py-2 text-center text-[10px] tracking-wider ${ready ? "border-[#22c55e]/70 text-[#22c55e] hover:bg-[#14251b]" : "pointer-events-none border-[#1e2936] text-[#71809a] opacity-60"}`}>{t("enter_command_center")}</Link><button onClick={() => window.dispatchEvent(new Event("orion:open-cio"))} className="rounded border border-[#ef4444]/70 px-3 py-2 text-[10px] tracking-wider text-[#ef4444]">{t("talk_to_cio")}</button><Link href="/" className="rounded border border-[#1e2936] px-3 py-2 text-center text-[10px] text-[#9db2d0]">{t("view_market")}</Link><Link href="/status" className="rounded border border-[#1e2936] px-3 py-2 text-center text-[10px] text-[#9db2d0]">{t("view_system")}</Link></div>
      <button onClick={() => void runChecks()} disabled={running} className="mt-4 w-full text-[10px] text-[#71809a] hover:text-white disabled:opacity-50">{running ? "COMPROBANDO…" : "VOLVER A COMPROBAR"}</button>
    </section>
  </div>;
}
