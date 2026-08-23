"use client";

// ORION COMMAND CENTER (P17-P19, P29-P30, P33-P36)
// Institutional mission-control layout: boot sequence, ticker, CIO wheel,
// intelligence feed, terminal chat, agent activity + system row.
// Light CSS-only animations; no render loops.

import { FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/api";
import { LANGUAGES, LangCode, useLanguage } from "@/lib/i18n";

type ActivityEntry = { agent: string; action: string; status: string };
type SourceRef = { field: string; source: string | null; ts: string | null };
type CioPayload = {
  reply?: string;
  routing?: { intent: string; asset: string | null };
  activity?: ActivityEntry[];
  sources?: SourceRef[];
  audit?: { verdict: string; gaps: string[] };
  scores?: {
    bias_score?: { total?: number; band?: string; missing_inputs?: string[] };
    trade_quality?: { total?: number; missing_inputs?: string[] };
    decision?: { status?: string; reasons?: string[] };
  };
};
type TickerRow = {
  symbol: string;
  price: number | null;
  change_pct: number | null;
  status: string;
};
type Intelligence = {
  latest_news: { title: string; source: string | null; relevance: string | null }[];
  macro_flag: { title: string; source: string | null } | null;
  liquidity_event: { asset: string | null; event: string } | null;
  risk_warnings: { message: string; severity: string }[];
  cio_decision: { asset: string | null; stance: string | null; summary: string | null };
};
type AgentRow = {
  agent_id: string;
  name: string;
  role: string;
  status: string;
  health: string;
  last_run: string | null;
  last_error: string | null;
};

const WHEEL_AGENTS = [
  "MACRO", "METALS", "CRYPTO", "EQUITIES", "LIQUIDITY",
  "POSITIONING", "CROSS-ASSET", "NEWS", "QUANT", "RISK", "AUDIT",
];

const AGENT_NODE_MAP: Record<string, string> = {
  "macro-strategist": "MACRO",
  "metals-analyst": "METALS",
  "crypto-analyst": "CRYPTO",
  "equities-analyst": "EQUITIES",
  "liquidity-analyst": "LIQUIDITY",
  "positioning-analyst": "POSITIONING",
  "crossasset-analyst": "CROSS-ASSET",
  "news-intelligence": "NEWS",
  "quant-architect": "QUANT",
  "risk-manager": "RISK",
  "audit-agent": "AUDIT",
};

const QUICK_ACTIONS: { key: string; message: string }[] = [
  { key: "analyze_gold", message: "Analiza XAUUSD" },
  { key: "analyze_xrp", message: "Analiza XRP" },
  { key: "analyze_nasdaq", message: "Analiza NASDAQ" },
  { key: "pre_london", message: "Dame el Pre-Londres" },
  { key: "pre_ny", message: "Dame el Pre-NY" },
  { key: "convene_desk", message: "Convoca la mesa para XAUUSD" },
  { key: "risk_check", message: "@risk revisa XAUUSD" },
  { key: "system_status", message: "estado del sistema" },
];

type BootCheck = { label: string; state: "WAIT" | "OK" | "DEGRADED" | "FAIL"; detail: string };

export default function CommandCenter() {
  const { lang, setLang, t, applyServerCatalogs } = useLanguage();
  const [booted, setBooted] = useState(false);
  const [boot, setBoot] = useState<BootCheck[]>([]);
  const [ticker, setTicker] = useState<TickerRow[]>([]);
  const [intel, setIntel] = useState<Intelligence | null>(null);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [systemOverall, setSystemOverall] = useState<string>("…");
  const [apiError, setApiError] = useState<string | null>(null);

  // terminal state
  const [messages, setMessages] = useState<{ author: string; content: string; original?: string }[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [lastCio, setLastCio] = useState<CioPayload | null>(null);
  const [autoTranslate, setAutoTranslate] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  // ---- i18n catalogs from API
  useEffect(() => {
    fetch(`${API_URL}/api/v1/i18n/catalogs`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((p) => p && applyServerCatalogs(p))
      .catch(() => undefined);
  }, [applyServerCatalogs]);

  // ---- boot sequence (P29): honest checks only
  const runBoot = useCallback(async () => {
    const checks: BootCheck[] = [];
    setBoot(checks);
    const push = async (
      label: string,
      fn: () => Promise<{ ok: boolean; degraded?: boolean; detail: string }>,
    ) => {
      let entry: BootCheck = { label, state: "WAIT", detail: "checking…" };
      setBoot((b) => [...b.filter((x) => x.label !== label), entry]);
      try {
        const res = await fn();
        entry = {
          label,
          state: res.ok ? (res.degraded ? "DEGRADED" : "OK") : "FAIL",
          detail: res.detail,
        };
      } catch {
        entry = { label, state: "FAIL", detail: "unreachable" };
      }
      setBoot((b) => [...b.filter((x) => x.label !== label), entry]);
    };

    await push("API", async () => {
      const r = await fetch(`${API_URL}/health`, { cache: "no-store" });
      return { ok: r.ok, detail: r.ok ? "HEALTHY" : `HTTP ${r.status}` };
    });
    await push("DATABASE", async () => {
      const s = await (await fetch(`${API_URL}/api/v1/system/status`, { cache: "no-store" })).json();
      setSystemOverall(s.overall);
      return {
        ok: !!s.database?.status,
        detail: `${s.database?.status ?? "?"} · ${s.database?.engine ?? ""}`,
      };
    });
    await push("MARKET FEEDS", async () => {
      const s = await (await fetch(`${API_URL}/api/v1/system/status`, { cache: "no-store" })).json();
      const yahoo = s.services?.find((x: { service: string }) => x.service.includes("yahoo"));
      const st = yahoo?.state ?? "UNKNOWN";
      return { ok: st === "HEALTHY", degraded: st !== "FAILED" && st !== "HEALTHY", detail: String(st) };
    });
    await push("CRYPTO", async () => {
      const s = await (await fetch(`${API_URL}/api/v1/system/status`, { cache: "no-store" })).json();
      const cb = s.services?.find((x: { service: string }) => x.service.includes("coinbase"));
      return { ok: cb?.state === "HEALTHY", detail: String(cb?.state ?? "?") };
    });
    await push("NEWS", async () => {
      const s = await (await fetch(`${API_URL}/api/v1/system/status`, { cache: "no-store" })).json();
      const nw = s.services?.find((x: { service: string }) => x.service.includes("news"));
      return { ok: nw?.state === "HEALTHY", degraded: nw?.state === "DEGRADED" || nw?.state === "STALE", detail: String(nw?.state ?? "?") };
    });
    await push("CFTC", async () => {
      const s = await (await fetch(`${API_URL}/api/v1/system/status`, { cache: "no-store" })).json();
      const cftc = s.services?.find((x: { service: string }) => x.service.includes("cftc"));
      const st = cftc?.state ?? "NOT_CONFIGURED";
      return { ok: true, degraded: st === "NOT_CONFIGURED", detail: st === "NOT_CONFIGURED" ? "ON-DEMAND / READY" : String(st) };
    });
    await push("CIO", async () => {
      const r = await fetch(`${API_URL}/api/v1/cio/agents`, { cache: "no-store" });
      return { ok: r.ok, detail: r.ok ? "READY" : `HTTP ${r.status}` };
    });
    await push("RISK", async () => {
      const r = await fetch(`${API_URL}/api/v1/trades/positions`, { cache: "no-store" });
      return { ok: r.ok, detail: r.ok ? "READY" : `HTTP ${r.status}` };
    });
    setApiError(null);
  }, []);

  useEffect(() => {
    if (!booted) void runBoot();
  }, [booted, runBoot]);

  // ---- polling: ticker every 60s, intelligence+agents every 30s
  useEffect(() => {
    if (!booted) return;
    const loadTicker = () =>
      fetch(`${API_URL}/api/v1/command/ticker`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => d && setTicker(d.ticker))
        .catch(() => setApiError(t("feed_degraded")));
    const loadIntel = () =>
      fetch(`${API_URL}/api/v1/command/intelligence`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => d && setIntel(d))
        .catch(() => undefined);
    const loadAgents = () =>
      fetch(`${API_URL}/api/v1/agents`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => d && Array.isArray(d.agents) && setAgents(d.agents))
        .catch(() => undefined);
    loadTicker();
    loadIntel();
    loadAgents();
    const tickT = setInterval(loadTicker, 60_000);
    const tickI = setInterval(loadIntel, 30_000);
    const tickA = setInterval(loadAgents, 30_000);
    return () => {
      clearInterval(tickT);
      clearInterval(tickI);
      clearInterval(tickA);
    };
  }, [booted, t]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ---- terminal send with auto-translate (P22)
  const sendContent = useCallback(
    async (content: string) => {
      if (!content || sending) return;
      setSending(true);
      try {
        const res = await fetch(`${API_URL}/api/v1/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content, room: "desk" }),
          cache: "no-store",
        });
        if (!res.ok) {
          setMessages((m) => [...m,
            { author: "system", content: `ERROR ${res.status} — ${t("api_offline")}` }]);
          return;
        }
        const payload = await res.json();
        let reply = payload.cio?.reply ?? payload.content ?? "(empty)";
        let original: string | undefined;
        if (payload.cio && autoTranslate && lang !== "es") {
          try {
            const tr = await fetch(`${API_URL}/api/v1/i18n/translate`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ text: reply, target_lang: lang }),
            }).then((r) => (r.ok ? r.json() : null));
            if (tr?.translated) {
              original = reply;
              reply = tr.text as string;
            }
          } catch {
            /* P23 — keep original on translator failure */
          }
        }
        setMessages((m) => [...m, { author: "user", content }, { author: payload.author ?? "orion-cio", content: reply, original }]);
        if (payload.cio) setLastCio(payload.cio);
      } finally {
        setSending(false);
      }
    },
    [sending, autoTranslate, lang, t],
  );

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const content = input.trim();
    setInput("");
    await sendContent(content);
  }

  // derived header chips
  const biasTotal = lastCio?.scores?.bias_score?.total;
  const biasBand = lastCio?.scores?.bias_score?.band ?? "—";
  const tqTotal = lastCio?.scores?.trade_quality?.total;
  const decision = lastCio?.scores?.decision?.status ?? "—";
  const activeAgents = new Set(
    (lastCio?.activity ?? [])
      .filter((a) => a.status === "ok")
      .map((a) => AGENT_NODE_MAP[a.agent])
      .filter(Boolean),
  );
  const cioStatus =
    sending ? "THINKING"
      : lastCio?.scores?.decision?.status === "NO_TRADE" || lastCio?.audit?.verdict === "RED"
        ? "RISK BLOCKED"
        : systemOverall === "OPERATIONAL"
          ? decision === "—" ? "READY" : "WAITING"
          : systemOverall === "DEGRADED" ? "DATA DEGRADED" : "READY";
  const sessionLabel = ticker.length > 0 ? sessionOfNow() : "…";

  if (!booted) {
    return <BootScreen boot={boot} onEnter={() => setBooted(true)} apiError={apiError} onRetry={runBoot} />;
  }

  return (
    <div className="flex flex-col gap-2 h-[calc(100vh-40px)] min-w-[900px]">
      {/* ===== top bar ===== */}
      <header className="panel px-3 py-2 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-baseline gap-3">
          <span className="text-[15px] font-bold tracking-[0.25em] text-red-500">ORION</span>
          <span className="text-[10px] tracking-[0.18em] text-[#71809a]">
            {t("institutional_desk")}
          </span>
        </div>
        <nav className="hidden md:flex items-center gap-3 text-[10px] text-[#9db2d0]">
          <a className="hover:text-white" href="/">OVERVIEW</a>
          <a className="hover:text-white" href="/desk">DESK</a>
          <a className="hover:text-white" href="/agents">AGENTS</a>
          <a className="hover:text-white text-[#38bdf8]" href="/command">{t("command_center")}</a>
          <a className="hover:text-white" href="/status">SYSTEM</a>
        </nav>
        <div className="flex items-center gap-2 text-[10px]">
          <LanguageMenu lang={lang} setLang={setLang} />
          <button
            onClick={() => setAutoTranslate((v) => !v)}
            className={`px-2 py-0.5 rounded border ${
              autoTranslate ? "border-[#22c55e]/60 text-[#22c55e]" : "border-[#1e2936] text-[#71809a]"
            }`}
            title={t("auto_translate")}
          >
            AUTO TRAD: {autoTranslate ? "ON" : "OFF"}
          </button>
        </div>
      </header>

      {/* ===== status chips ===== */}
      <div className="panel px-3 py-1.5 grid grid-cols-3 md:grid-cols-6 gap-x-4 gap-y-1 text-[10px]">
        <Chip label="SESSION" value={sessionLabel} tone="blue" />
        <Chip label="REGIME" value={regimeOf(lastCio)} />
        <Chip label="BIAS SCORE" value={biasTotal != null ? `${biasTotal} · ${biasBand}` : "—"} tone="blue" />
        <Chip label="TRADE QUALITY" value={tqTotal != null ? String(tqTotal) : "—"} tone="amber" />
        <Chip label="DECISION" value={decision} tone={decision === "TRADE" ? "green" : decision === "NO_TRADE" ? "red" : "amber"} />
        <Chip label="CIO" value={cioStatus} tone={cioStatus === "DATA DEGRADED" || cioStatus === "RISK BLOCKED" ? "amber" : "green"} />
      </div>

      {/* ===== ticker ===== */}
      <div className="panel px-2 py-1 overflow-x-auto">
        <div className="flex gap-4 text-[11px] whitespace-nowrap">
          {(ticker.length ? ticker : FALLBACK_TICKER).map((row) => (
            <span key={row.symbol} className="inline-flex items-baseline gap-1.5">
              <span className="text-[#9db2d0] tracking-wide">{row.symbol.replace("USD", "")}</span>
              <span>{row.price != null ? fmtPrice(row.price) : "N/A"}</span>
              {row.change_pct != null && (
                <span className={row.change_pct >= 0 ? "text-[#22c55e]" : "text-[#ef4444]"}>
                  {row.change_pct >= 0 ? "▲" : "▼"}{Math.abs(row.change_pct).toFixed(2)}%
                </span>
              )}
              <span className={`text-[8px] ${row.status === "LIVE" ? "text-[#22c55e]" : row.status === "STALE" ? "text-[#f59e0b]" : "text-[#71809a]"}`}>
                ●{row.status === "LIVE" ? "" : row.status}
              </span>
            </span>
          ))}
        </div>
      </div>

      {/* ===== main grid ===== */}
      <div className="grid grid-cols-12 gap-2 flex-1 min-h-0">
        {/* left: timeline + quick actions */}
        <aside className="col-span-3 xl:col-span-2 panel p-2 hidden lg:flex flex-col gap-2 min-h-0">
          <div className="panel-title !px-0 !pt-0">TIMELINE</div>
          <Timeline activity={lastCio?.activity ?? []} />
          <div className="mt-auto pt-2 flex flex-col gap-1.5">
            {QUICK_ACTIONS.map((a) => (
              <button
                key={a.key}
                disabled={sending}
                onClick={() => void sendContent(a.message)}
                className="text-left text-[10px] px-2 py-1 rounded border border-[#1e2936] text-[#9db2d0]
                           hover:text-white hover:border-[#38bdf8] disabled:opacity-50 transition-colors"
              >
                ▸ {t(a.key)}
              </button>
            ))}
          </div>
        </aside>

        {/* center: CIO wheel */}
        <section className="col-span-12 lg:col-span-6 xl:col-span-7 panel relative min-h-[380px] overflow-hidden">
          <div className="panel-title">ORION CIO — MULTI-AGENT CORE</div>
          <CioWheel agents={WHEEL_AGENTS} active={activeAgents} thinking={sending} />
        </section>

        {/* right: intelligence */}
        <aside className="col-span-12 lg:col-span-3 panel p-2 flex flex-col gap-2 min-h-0 overflow-y-auto">
          <div className="panel-title !px-0 !pt-0">{t("intelligence")}</div>
          {!intel && <p className="text-[10px] text-[#71809a]">waiting for feed…</p>}
          {intel && (
            <>
              <IntelBlock title="MACRO FLAG">
                {intel.macro_flag ? (
                  <p>▸ [{intel.macro_flag.source}] {intel.macro_flag.title}</p>
                ) : <p className="muted">NOT AVAILABLE</p>}
              </IntelBlock>
              <IntelBlock title="NEWS">
                {intel.latest_news.slice(0, 3).map((n, i) => (
                  <p key={i}>[{n.relevance ?? "?"}] {n.title}</p>
                ))}
              </IntelBlock>
              <IntelBlock title="LIQUIDITY EVENT">
                {intel.liquidity_event?.event
                  ? <p>▸ {intel.liquidity_event.asset}: {intel.liquidity_event.event}</p>
                  : <p className="muted">none mapped</p>}
              </IntelBlock>
              <IntelBlock title="RISK WARNING">
                {intel.risk_warnings.length > 0
                  ? intel.risk_warnings.map((w, i) => <p key={i}>⚠ {w.message}</p>)
                  : <p className="muted">none open</p>}
              </IntelBlock>
              <IntelBlock title="LAST CIO DECISION">
                {intel.cio_decision.summary
                  ? <p>▸ {intel.cio_decision.asset}: {intel.cio_decision.stance} — {intel.cio_decision.summary}</p>
                  : <p className="muted">no CIO runs yet</p>}
              </IntelBlock>
            </>
          )}
        </aside>
      </div>

      {/* ===== terminal + activity ===== */}
      <div className="grid grid-cols-12 gap-2" style={{ height: "34%" }}>
        <section className="col-span-8 lg:col-span-7 panel flex flex-col min-h-0">
          <div className="panel-title flex justify-between">
            <span>{t("terminal")} — ORION CIO</span>
            <span className="normal-case tracking-normal">{sending ? "thinking…" : ""}</span>
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
            {messages.length === 0 && (
              <p className="text-[10px] text-[#71809a]">
                Escribe al CIO: «Analiza oro» · «Convoca la mesa» · «Dame el Pre-NY» · «Vigila XAUUSD»
              </p>
            )}
            {messages.map((m, i) => (
              <p key={i} className="text-[11px] leading-relaxed whitespace-pre-wrap">
                <span className={m.author === "user" ? "text-[#38bdf8]"
                  : m.author === "system" ? "text-[#ef4444]" : "text-[#22c55e]"}>
                  [{m.author}]
                </span>{" "}
                {m.content.split("\n")[0]}
                {m.content.includes("\n") && (
                  <details className="ml-2 inline-block align-top">
                    <summary className="text-[9px] text-[#71809a] cursor-pointer hover:text-white select-none">expand</summary>
                    <span className="block border-l border-[#1e2936] pl-2 mt-1">{m.content.split("\n").slice(1).join("\n")}</span>
                  </details>
                )}
                {m.original && (
                  <details className="ml-2 inline-block align-top">
                    <summary className="text-[9px] text-[#71809a] cursor-pointer hover:text-white select-none">{t("view_original")}</summary>
                    <span className="block border-l border-[#1e2936] pl-2 mt-1 whitespace-pre-wrap">{m.original}</span>
                  </details>
                )}
              </p>
            ))}
            <div ref={bottomRef} />
          </div>
          <form onSubmit={onSubmit} className="flex gap-1.5 p-2 border-t border-[#1e2936]">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={sending}
              placeholder="mensaje para ORION CIO…"
              className="flex-1 bg-[#10161f] border border-[#1e2936] rounded px-2.5 py-1.5 text-[11px]
                         outline-none focus:border-[#38bdf8]"
            />
            <button type="submit" disabled={sending}
              className="bg-[#141c28] border border-[#1e2936] rounded px-4 text-[10px] tracking-widest
                         hover:bg-[#1e2936] disabled:opacity-50">
              {t("send")}
            </button>
          </form>
        </section>

        <section className="col-span-4 lg:col-span-5 panel p-2 overflow-y-auto min-h-0">
          <div className="panel-title !px-0 !pt-0">{t("agent_activity")}</div>
          <table className="w-full text-[10px]">
            <tbody>
              {agents.slice(0, 15).map((a) => (
                <tr key={a.agent_id} className="border-b border-[#131a24]/60">
                  <td className="py-0.5 pr-2 text-[#cbd5e1]">{a.name}</td>
                  <td className={a.health === "NEVER_RUN" ? "text-[#71809a]" : a.last_error ? "text-[#f59e0b]" : "text-[#22c55e]"}>
                    {a.last_error ? "ERROR" : a.health}
                  </td>
                  <td className="text-right text-[#71809a]">{fmtAgo(a.last_run)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="panel-title !px-0 mt-2">SYSTEM</div>
          <p className="text-[10px] text-[#9db2d0]">
            API <Dot ok={systemOverall === "OPERATIONAL"} /> · DB{" "}
            <Dot ok /> · OVERALL <span className={
              systemOverall === "OPERATIONAL" ? "text-[#22c55e]" : "text-[#f59e0b]"
            }>{systemOverall}</span>
          </p>
        </section>
      </div>

      {apiError && (
        <div className="fixed bottom-3 right-3 z-50 panel px-3 py-2 text-[11px] border-[#f59e0b]/60 text-[#f59e0b]">
          ⚠ {t("feed_degraded")} — retrying automatically
        </div>
      )}
    </div>
  );
}

/* =============================================================== pieces */

function Chip({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "green" | "red" | "amber" | "blue" }) {
  const color = tone === "green" ? "text-[#22c55e]" : tone === "red" ? "text-[#ef4444]"
    : tone === "amber" ? "text-[#f59e0b]" : tone === "blue" ? "text-[#38bdf8]" : "text-[#c9d4e3]";
  return (
    <span className="flex gap-1.5 items-baseline">
      <span className="text-[#71809a] tracking-wider">{label}</span>
      <span className={`${color} truncate`}>{value}</span>
    </span>
  );
}

function Dot({ ok }: { ok: boolean }) {
  return <span className={ok ? "text-[#22c55e]" : "text-[#f59e0b]"}>●</span>;
}

const FALLBACK_TICKER: TickerRow[] = ["XAUUSD", "DXY", "US10Y", "VIX", "NQ", "SPX", "BTCUSD", "XRPUSD"]
  .map((s) => ({ symbol: s, price: null, change_pct: null, status: "…" }));

function fmtPrice(p: number): string {
  if (p >= 1000) return p.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (p >= 10) return p.toFixed(3);
  return p.toFixed(4);
}

function fmtAgo(iso: string | null): string {
  if (!iso) return "never";
  const then = Date.parse(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  if (Number.isNaN(then)) return "—";
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  if (h < 48) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

function sessionOfNow(): string {
  const h = new Date().getUTCHours();
  const m = new Date().getUTCMinutes();
  const t = h * 60 + m;
  if (t >= 13 * 60 + 30 && t < 20 * 60) return "NY";
  if (t >= 8 * 60 && t < 16 * 60) return "LONDON";
  if (t < 8 * 60) return "ASIA";
  return "CLOSED";
}

function regimeOf(cio: CioPayload | null): string {
  const line = (cio?.reply ?? "").split("\n").find((l) => l.startsWith("MARKET STATE:") || l.startsWith("REGIME:"));
  if (!line) return "—";
  const m = line.match(/regime=([A-Z_]+)/);
  return m ? m[1] : "—";
}

function LanguageMenu({ lang, setLang }: { lang: LangCode; setLang: (l: LangCode) => void }) {
  const current = LANGUAGES.find((l) => l.code === lang) ?? LANGUAGES[0];
  return (
    <label className="relative inline-flex items-center gap-1 cursor-pointer group">
      <span className="text-[#71809a]">LANGUAGE:</span>
      <select
        value={lang}
        onChange={(e) => setLang(e.target.value as LangCode)}
        className="appearance-none bg-transparent border border-[#1e2936] rounded pl-1.5 pr-4 py-0.5
                   text-[10px] tracking-wider text-[#c9d4e3] focus:outline-none focus:border-[#38bdf8]"
        aria-label="language"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code} className="bg-[#10161f]">
            {l.code.toUpperCase()}
          </option>
        ))}
      </select>
      <span className="pointer-events-none absolute right-1 text-[8px] text-[#71809a] group-hover:text-white">▼</span>
      <span className="sr-only">{current.name}</span>
    </label>
  );
}

function Timeline({ activity }: { activity: ActivityEntry[] }) {
  if (activity.length === 0) {
    return <p className="text-[10px] text-[#71809a]">no runs yet in this session</p>;
  }
  return (
    <ul className="space-y-1 overflow-y-auto">
      {activity.slice(-14).map((a, i) => (
        <li key={i} className="text-[10px] leading-snug flex gap-1.5">
          <span className={a.status === "ok" ? "text-[#22c55e]"
            : a.status === "error" || a.status === "failed" ? "text-[#ef4444]" : "text-[#f59e0b]"}>
            {a.status === "ok" ? "✓ DONE" : a.status === "error" || a.status === "failed" ? "✗ FAILED" : "⚠ WARN"}
          </span>
          <span className="text-[#cbd5e1]">{a.agent}</span>
        </li>
      ))}
    </ul>
  );
}

function IntelBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="border-t border-[#131a24] pt-1.5 first:border-0 first:pt-0">
      <p className="text-[9px] tracking-[0.14em] text-[#5b6b85] mb-0.5">{title}</p>
      <div className="space-y-0.5 text-[10px] text-[#c9d4e3] [&_.muted]:text-[#5b6b85]">{children}</div>
    </div>
  );
}

function CioWheel({ agents, active, thinking }: { agents: string[]; active: Set<string>; thinking: boolean }) {
  const cx = 50, cy = 50, rx = 36, ry = 30;
  const pos = agents.map((name, i) => {
    const angle = (i / agents.length) * Math.PI * 2 - Math.PI / 2;
    return { name, x: cx + rx * Math.cos(angle), y: cy + ry * Math.sin(angle) };
  });
  return (
    <svg viewBox="0 0 100 62" className="w-full h-[calc(100%-28px)]" preserveAspectRatio="xMidYMid meet">
      {pos.map((p) => (
        <line key={`ln-${p.name}`} x1={cx} y1={cy * 0.98} x2={p.x} y2={p.y * 0.98}
          stroke={active.has(p.name) ? "#38bdf8aa" : "#1e2936"}
          strokeWidth={active.has(p.name) ? 0.45 : 0.25} />
      ))}
      {/* orbit rings */}
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke="#16202e" strokeWidth={0.3} strokeDasharray="1.5 1.5" />
      <ellipse cx={cx} cy={cy} rx={rx * 0.72} ry={ry * 0.72} fill="none" stroke="#16202e" strokeWidth={0.3} />
      {/* central node */}
      <circle cx={cx} cy={cy} r={7.2} fill="#10161f" stroke="#ef4444" strokeWidth={0.5}
        className={thinking ? "orion-pulse" : ""} />
      <text x={cx} y={cy - 0.4} textAnchor="middle" fontSize={2.6} fill="#ffffff" fontWeight={700} letterSpacing={0.35}>
        ORION
      </text>
      <text x={cx} y={cy + 2.6} textAnchor="middle" fontSize={1.9} fill={thinking ? "#38bdf8" : "#71809a"}>
        {thinking ? "THINKING" : "CIO"}
      </text>
      {/* agent nodes */}
      {pos.map((p) => (
        <g key={p.name} className={active.has(p.name) ? "orion-node-active" : undefined}>
          <circle cx={p.x} cy={p.y} r={3.4} fill="#141c28"
            stroke={active.has(p.name) ? "#22c55e" : "#2a3a52"} strokeWidth={0.35} />
          <text x={p.x} y={p.y + 1} textAnchor="middle" fontSize={1.75}
            fill={active.has(p.name) ? "#22c55e" : "#9db2d0"}>
            {p.name.length > 8 ? p.name.slice(0, 7) + "." : p.name}
          </text>
        </g>
      ))}
    </svg>
  );
}

function BootScreen({ boot, onEnter, apiError, onRetry }: {
  boot: BootCheck[];
  onEnter: () => void;
  apiError: string | null;
  onRetry: () => void | Promise<void>;
}) {
  const ready = boot.length >= 8 && boot.every((b) => b.state !== "WAIT");
  const failed = boot.some((b) => b.state === "FAIL");
  return (
    <div className="min-h-[calc(100vh-40px)] flex items-center justify-center">
      <div className="panel w-full max-w-md p-6">
        <div className="flex items-center gap-3 mb-5">
          <OrionMark size={44} />
          <div>
            <h1 className="text-lg font-bold tracking-[0.3em] text-red-500 leading-none">ORION</h1>
            <p className="text-[10px] tracking-[0.2em] text-[#71809a] mt-1">INITIALIZING…</p>
          </div>
        </div>
        <ul className="space-y-1 text-[11px] font-mono">
          {boot.length === 0 && <li className="text-[#71809a]">contacting services…</li>}
          {boot.map((b) => (
            <li key={b.label} className="flex justify-between gap-3">
              <span className="text-[#c9d4e3]">{b.label.padEnd(10, ".")}</span>
              <span className={
                b.state === "OK" ? "text-[#22c55e]"
                  : b.state === "DEGRADED" ? "text-[#f59e0b]"
                    : b.state === "FAIL" ? "text-[#ef4444]" : "text-[#71809a] animate-pulse"
              }>
                {b.state === "WAIT" ? "…" : b.detail || b.state}
              </span>
            </li>
          ))}
        </ul>
        <button
          onClick={() => void onRetry()}
          className="mt-5 w-full text-[11px] tracking-widest py-2 rounded border border-[#1e2936]
                     text-[#9db2d0] hover:border-[#38bdf8] hover:text-white transition-colors"
        >
          RE-CHECK
        </button>
        <button
          onClick={onEnter}
          disabled={!ready}
          className={`mt-2 w-full text-[11px] tracking-[0.2em] py-2 rounded border transition-colors
                     ${failed ? "border-[#f59e0b]/70 text-[#f59e0b]" : "border-[#22c55e]/60 text-[#22c55e]"}
                     enabled:hover:bg-[#14251b] disabled:opacity-40`}
        >
          {ready ? "ENTER COMMAND CENTER" : "CHECKING SERVICES…"}
        </button>
        {apiError && (
          <p className="mt-2 text-[10px] text-[#f59e0b]">⚠ {apiError}</p>
        )}
        <p className="mt-3 text-[9px] text-[#5b6b85] text-center">
          PAPER MODE ONLY — NO LIVE EXECUTION · states shown are real service states
        </p>
      </div>
    </div>
  );
}

function OrionMark({ size = 32 }: { size?: number }) {
  return (
    <img src="/orion-icon.svg" width={size} height={size} alt="ORION" />
  );
}
