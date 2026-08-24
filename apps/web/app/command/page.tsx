"use client";

// ORION COMMAND CENTER (P17-P19, P29-P30, P33-P36)
// Institutional mission-control layout: boot sequence, ticker, CIO wheel,
// intelligence feed, terminal chat, agent activity + system row.
// Light CSS-only animations; no render loops.

import { FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/api";
import { LANGUAGES, LangCode, useLanguage } from "@/lib/i18n";
import { buildCioNarrationPhrases, useMarketVoiceAlerts, useVoiceAnnouncer } from "@/lib/voice";
import OrionCoreScene, { type OrionAssetVolume } from "@/components/OrionCoreScene";

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
  volume?: number | null;
  relative_volume?: number | null;
};
type Intelligence = {
  latest_news: { title: string; source: string | null; relevance: string | null }[];
  macro_flag: { title: string; source: string | null } | null;
  liquidity_event: { asset: string | null; event: string } | null;
  risk_warnings: { message: string; severity: string }[];
  cio_decision: { asset: string | null; stance: string | null; summary: string | null };
};
type FaroStatus = {
  configured: boolean;
  endpoint_configured: boolean;
  last_signal: { status: string; detail: string; ts: string } | null;
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
type Opportunity = {
  setup_id: string; symbol: string; setup: string; direction: string; state: string;
  opportunity: number; bias: number | null; trade_quality: number | null;
  adx: number | string | null; adx_slope: number | string | null;
  relative_volume: number | null; rr: number | null;
  stat_edge: { status?: string; sample_size?: number; expectancy?: number | null } | null;
  data_quality: string | null; missing_inputs: string[]; last_update: string | null;
};

const WHEEL_AGENTS = [
  "MACRO", "METALS", "FOREX", "CRYPTO", "EQUITIES", "LIQUIDITY",
  "POSITIONING", "CROSS-ASSET", "NEWS", "QUANT", "RISK", "AUDIT",
];

const AGENT_NODE_MAP: Record<string, string> = {
  "macro-strategist": "MACRO",
  "metals-analyst": "METALS",
  "forex-analyst": "FOREX",
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
  { key: "analyze_forex", message: "Analiza EURUSD" },
  { key: "pre_london", message: "Dame el Pre-Londres" },
  { key: "pre_ny", message: "Dame el Pre-NY" },
  { key: "convene_desk", message: "Convoca la mesa para XAUUSD" },
  { key: "risk_check", message: "@risk revisa XAUUSD" },
  { key: "system_status", message: "estado del sistema" },
];

type BootCheck = { label: string; state: "WAIT" | "OK" | "DEGRADED" | "FAIL"; detail: string };

export default function CommandCenter() {
  const { lang, setLang, t, applyServerCatalogs } = useLanguage();
  const voice = useVoiceAnnouncer(lang);
  const [booted, setBooted] = useState(false);
  const [boot, setBoot] = useState<BootCheck[]>([]);
  const [ticker, setTicker] = useState<TickerRow[]>([]);
  const [intel, setIntel] = useState<Intelligence | null>(null);
  const [radar, setRadar] = useState<Opportunity[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [faro, setFaro] = useState<FaroStatus | null>(null);
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
    const loadRadar = () =>
      fetch(`${API_URL}/api/v1/scanner/radar`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => d && setRadar(d.opportunities ?? []))
        .catch(() => undefined);
    const loadFaro = () =>
      fetch(`${API_URL}/api/v1/settings/connections/faro/status`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => d?.faro && setFaro(d.faro))
        .catch(() => undefined);
    loadTicker();
    loadIntel();
    loadAgents();
    loadRadar();
    loadFaro();
    const tickT = setInterval(loadTicker, 60_000);
    const tickI = setInterval(loadIntel, 30_000);
    const tickA = setInterval(loadAgents, 30_000);
    const tickR = setInterval(loadRadar, 5_000);
    const tickF = setInterval(loadFaro, 30_000);
    return () => {
      clearInterval(tickT);
      clearInterval(tickI);
      clearInterval(tickA);
      clearInterval(tickR);
      clearInterval(tickF);
    };
  }, [booted, t]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ---- voice alerts (P38): watches the state already polled above, no extra fetches
  useMarketVoiceAlerts({
    lang,
    enabled: voice.enabled,
    announce: voice.announce,
    ticker,
    radar,
    intel,
    prioritySymbols: PRIORITY_SYMBOLS,
  });

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
        if (payload.cio && autoTranslate) {
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
        if (payload.cio) {
          setLastCio(payload.cio);
          // P40 — voz interactiva: narra lo que la mesa (CIO + especialistas)
          // acaba de concluir, usando el texto real ya generado (nada inventado).
          if (payload.cio.reply) {
            for (const phrase of buildCioNarrationPhrases(payload.cio.reply, lang)) {
              voice.announce(phrase);
            }
          }
        }
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

  // ---- P41/P42: real per-asset volume intensity feeding the 3D core spiral —
  // relative_volume comes straight from the scanner via the ticker poll;
  // 0 (calm/no data) when a symbol has no reading yet, never fabricated.
  const assetVolumes: OrionAssetVolume[] = SPIRAL_ASSETS.map((a) => {
    const row = ticker.find((r) => r.symbol === a.symbol);
    const rv = row?.relative_volume ?? null;
    const intensity = rv != null ? Math.max(0, Math.min(1, rv / 2.2)) : 0;
    return { symbol: a.symbol, color: a.hex, intensity };
  });

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
          <button
            onClick={() => voice.setEnabled(!voice.enabled)}
            disabled={!voice.supported}
            className={`px-2 py-0.5 rounded border disabled:opacity-40 ${
              voice.enabled ? "border-[#22c55e]/60 text-[#22c55e]" : "border-[#1e2936] text-[#71809a]"
            }`}
            title={
              voice.supported
                ? voice.openaiReady
                  ? "Alertas de voz de ORION — motor OpenAI TTS (Settings > Voz IA)"
                  : "Alertas de voz de ORION — voz del navegador (configura Settings > Voz IA para mejorarla)"
                : "Tu navegador no soporta síntesis de voz"
            }
          >
            VOZ: {voice.supported ? (voice.enabled ? `ON${voice.openaiReady ? " · IA" : ""}` : "OFF") : "N/A"}
          </button>
        </div>
      </header>

      {/* ===== status chips ===== */}
      <div className="panel px-3 py-1.5 grid grid-cols-3 md:grid-cols-6 gap-x-4 gap-y-1 text-[10px]">
        <Chip label={t("session")} value={sessionLabel} tone="blue" />
        <Chip label={t("regime")} value={regimeOf(lastCio)} />
        <Chip label={t("bias_score")} value={biasTotal != null ? `${biasTotal} · ${biasBand}` : "—"} tone="blue" />
        <Chip label={t("trade_quality")} value={tqTotal != null ? String(tqTotal) : "—"} tone="amber" />
        <Chip label={t("decision")} value={decision} tone={decision === "TRADE" ? "green" : decision === "NO_TRADE" ? "red" : "amber"} />
        <Chip label="CIO" value={cioStatus} tone={cioStatus === "DATA DEGRADED" || cioStatus === "RISK BLOCKED" ? "amber" : "green"} />
      </div>

      {/* ===== ticker ===== */}
      <div className="panel px-2 py-1 overflow-x-auto">
        <div className="flex gap-4 text-[11px] whitespace-nowrap">
          {(ticker.length ? ticker : FALLBACK_TICKER).map((row) => (
            <span key={row.symbol} className={`inline-flex items-baseline gap-1.5 ${
              PRIORITY_SYMBOLS.has(row.symbol) ? "orion-priority-symbol" : ""
            }`}>
              {PRIORITY_SYMBOLS.has(row.symbol) && <span className="text-[#38bdf8] orion-pulse">◆</span>}
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

      <section className="panel overflow-x-auto">
        <div className="panel-title flex items-center justify-between">
          <span>LIVE OPPORTUNITY RADAR</span><span className="normal-case tracking-normal text-[#22c55e]">SCANNING · {radar.length} candidates</span>
        </div>
        <table className="w-full min-w-[1250px] text-[9px]"><thead className="text-[#71809a]"><tr>
          <th className="px-2 py-1 text-left">ASSET</th><th className="text-left">SETUP</th><th>DIR</th><th>STATE</th><th>OPP</th><th>BIAS</th><th>QUALITY</th><th>ADX</th><th>ADX SLOPE</th><th>REL VOL</th><th>R:R</th><th>STAT EDGE</th><th>DATA</th><th>AGE</th>
        </tr></thead><tbody>{radar.slice(0, 15).map((item) => <tr key={item.setup_id} title={item.missing_inputs.join(", ")} className="border-t border-[#1e2936] text-center"><td className="px-2 py-1 text-left text-[#c9d4e3]">{item.symbol}</td><td className="text-left text-[#9db2d0]">{item.setup}</td><td>{item.direction}</td><td className={stateTone(item.state)}>{item.state}</td><td>{item.opportunity.toFixed(0)}</td><td>{item.bias ?? "—"}</td><td>{item.trade_quality ?? "—"}</td><td>{typeof item.adx === "number" ? item.adx.toFixed(1) : "INSUFFICIENT"}</td><td>{typeof item.adx_slope === "number" ? item.adx_slope.toFixed(2) : "—"}</td><td>{item.relative_volume?.toFixed(2) ?? "N/A"}</td><td>{item.rr?.toFixed(2) ?? "N/A"}</td><td>{item.stat_edge?.status === "AVAILABLE" ? item.stat_edge.expectancy?.toFixed(2) : `N=${item.stat_edge?.sample_size ?? 0}`}</td><td>{item.data_quality ?? "UNKNOWN"}</td><td className="text-[#71809a]">{fmtAgo(item.last_update)}</td></tr>)}</tbody></table>
        {radar.length === 0 && <p className="px-2 py-2 text-[10px] text-[#71809a]">NO QUALIFIED SETUP · esperando datos y reacción confirmable</p>}
      </section>

      {/* ===== main grid ===== */}
      <div className="grid grid-cols-12 gap-2 flex-1 min-h-0">
        {/* left: timeline + quick actions */}
        <aside className="col-span-3 xl:col-span-2 panel p-2 hidden lg:flex flex-col gap-2 min-h-0">
          <div className="panel-title !px-0 !pt-0">{t("timeline")}</div>
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

        {/* center: ORION core — 3D particle visual + live HUD overlays */}
        <section className="col-span-12 lg:col-span-6 xl:col-span-7 panel relative min-h-[420px] overflow-hidden">
          <div className="panel-title flex items-center justify-between">
            <span>ORION CIO — NÚCLEO MULTIAGENTE</span>
            <span className="normal-case tracking-normal text-[#cdf26a]">
              {activeAgents.size}/{WHEEL_AGENTS.length} ACTIVOS
            </span>
          </div>
          <div className="orion-wheel-glow" />
          <OrionCoreScene
            thinking={sending}
            activeCount={activeAgents.size}
            totalCount={WHEEL_AGENTS.length}
            assets={assetVolumes}
          />
          <div className="absolute inset-x-0 top-9 bottom-2 px-3 py-2 flex flex-col justify-between pointer-events-none">
            <div className="flex justify-between items-start gap-2 flex-wrap">
              <HudBox label="SESSION" value={sessionLabel} />
              <HudBox label="REGIME" value={regimeOf(lastCio)} />
              <HudBox label="BIAS" value={biasTotal != null ? `${biasTotal} · ${biasBand}` : "—"} />
            </div>
            <div className="flex justify-center">
              <span className="text-[10px] tracking-[0.35em] text-[#cdf26a]/90 select-none">
                {sending ? "ORION · THINKING…" : "ORION"}
              </span>
            </div>
            <div className="flex justify-between items-end gap-2 flex-wrap">
              <HudBox
                label="DECISION"
                value={decision}
                tone={decision === "TRADE" ? "green" : decision === "NO_TRADE" ? "red" : "amber"}
              />
              <VolumeFlowBox ticker={ticker} assets={SPIRAL_ASSETS} />
              <HudBox label="AGENTS" value={`${activeAgents.size}/${WHEEL_AGENTS.length}`} />
            </div>
          </div>
        </section>

        {/* right: intelligence */}
        <aside className="col-span-12 lg:col-span-3 panel p-2 flex flex-col gap-2 min-h-0 overflow-y-auto">
          <div className="panel-title !px-0 !pt-0">{t("intelligence")}</div>
          {!intel && <p className="text-[10px] text-[#71809a]">waiting for feed…</p>}
          {intel && (
            <>
              <IntelBlock title={t("macro_flag")}>
                {intel.macro_flag ? (
                  <p>▸ [{intel.macro_flag.source}] {intel.macro_flag.title}</p>
                ) : <p className="muted">NOT AVAILABLE</p>}
              </IntelBlock>
              <IntelBlock title={t("news")}>
                {intel.latest_news.slice(0, 3).map((n, i) => (
                  <p key={i}>[{n.relevance ?? "?"}] {n.title}</p>
                ))}
              </IntelBlock>
              <IntelBlock title={t("liquidity_event")}>
                {intel.liquidity_event?.event
                  ? <p>▸ {intel.liquidity_event.asset}: {intel.liquidity_event.event}</p>
                  : <p className="muted">none mapped</p>}
              </IntelBlock>
              <IntelBlock title={t("risk_warning")}>
                {intel.risk_warnings.length > 0
                  ? intel.risk_warnings.map((w, i) => <p key={i}>⚠ {w.message}</p>)
                  : <p className="muted">none open</p>}
              </IntelBlock>
              <IntelBlock title={t("last_cio_decision")}>
                {intel.cio_decision.summary
                  ? <p>▸ {intel.cio_decision.asset}: {intel.cio_decision.stance} — {intel.cio_decision.summary}</p>
                  : <p className="muted">no CIO runs yet</p>}
              </IntelBlock>
              <IntelBlock title="FARO">
                {!faro && <p className="muted">loading…</p>}
                {faro && !faro.configured && (
                  <p className="muted">not configured — <a href="/settings" className="text-[#38bdf8] hover:underline">Settings &gt; Faro</a></p>
                )}
                {faro && faro.configured && !faro.last_signal && (
                  <p className="muted">configured · no signals sent yet</p>
                )}
                {faro && faro.configured && faro.last_signal && (
                  <p>
                    <span className={
                      faro.last_signal.status === "SENT" ? "text-[#22c55e]"
                        : faro.last_signal.status === "FAILED" ? "text-[#ef4444]"
                          : "text-[#38bdf8]"
                    }>{faro.last_signal.status}</span>{" "}
                    {!faro.endpoint_configured && <span className="muted">(demo — sin endpoint)</span>}{" "}
                    {faro.last_signal.detail}
                  </p>
                )}
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
              <div key={i} className="text-[11px] leading-relaxed whitespace-pre-wrap">
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
              </div>
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
           <div className="panel-title !px-0 mt-2">{t("system")}</div>
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

function HudBox({
  label, value, tone = "default",
}: { label: string; value: string; tone?: "default" | "green" | "red" | "amber" | "blue" }) {
  const color = tone === "green" ? "text-[#22c55e]" : tone === "red" ? "text-[#ef4444]"
    : tone === "amber" ? "text-[#f59e0b]" : tone === "blue" ? "text-[#38bdf8]" : "text-[#cdf26a]";
  return (
    <div className="orion-hud-box">
      <span className="orion-hud-label">{label}</span>
      <span className={`orion-hud-value ${color}`}>{value}</span>
    </div>
  );
}

function VolumeFlowBox({
  ticker, assets,
}: { ticker: TickerRow[]; assets: { symbol: string; label: string; color: string }[] }) {
  return (
    <div className="orion-hud-box orion-hud-box-wide">
      <span className="orion-hud-label">VOLUME FLOW · REL. VOL EN VIVO</span>
      <div className="flex items-end gap-3 h-14 mt-1">
        {assets.map((a) => {
          const row = ticker.find((r) => r.symbol === a.symbol);
          const rv = row?.relative_volume ?? null;
          const pct = rv != null ? Math.max(6, Math.min(100, (rv / 2.2) * 100)) : 0;
          return (
            <div
              key={a.symbol}
              className="flex flex-col items-center gap-1 w-9"
              title={rv != null ? `${a.symbol}: volumen relativo ${rv.toFixed(2)}×` : `${a.symbol}: sin dato de volumen todavía`}
            >
              <div className="w-2.5 rounded-sm bg-[#1e2936] flex items-end overflow-hidden" style={{ height: 32 }}>
                <div
                  className="w-full transition-[height] duration-500"
                  style={{ height: rv != null ? `${pct}%` : "2px", opacity: rv != null ? 0.95 : 0.3, background: a.color }}
                />
              </div>
              <span className="text-[8px] font-semibold" style={{ color: a.color }}>{a.label}</span>
              <span className="text-[8px] text-[#9db2d0] tabular-nums">{rv != null ? `${rv.toFixed(2)}×` : "N/A"}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const FALLBACK_TICKER: TickerRow[] = [
  "XAUUSD", "NQ", "EURUSD", "GBPUSD", "DXY", "US10Y", "VIX", "SPX", "BTCUSD", "XRPUSD",
].map((s) => ({ symbol: s, price: null, change_pct: null, status: "…" }));

const PRIORITY_SYMBOLS = new Set(["XAUUSD", "NQ", "EURUSD", "GBPUSD"]);

// P42: per-asset colors for the 3D volume spiral + the volume-flow panel.
// XAUUSD/BTCUSD/XRPUSD colors per the user's explicit request (fucsia/naranja/azul);
// NQ/EURUSD/GBPUSD get their own distinct colors so every strand reads at a glance.
// Note: EURUSD/GBPUSD honestly show N/A most of the time — the scanner's relative-volume
// feature only covers XAUUSD/NQ/BTCUSD/XRPUSD today (spot FX has no centralized volume).
const SPIRAL_ASSETS: { symbol: string; label: string; color: string; hex: number }[] = [
  { symbol: "XAUUSD", label: "XAU", color: "#e930ff", hex: 0xe930ff },
  { symbol: "NQ", label: "NQ", color: "#22d3ee", hex: 0x22d3ee },
  { symbol: "BTCUSD", label: "BTC", color: "#ff9d2f", hex: 0xff9d2f },
  { symbol: "XRPUSD", label: "XRP", color: "#3b82f6", hex: 0x3b82f6 },
  { symbol: "EURUSD", label: "EUR", color: "#a78bfa", hex: 0xa78bfa },
  { symbol: "GBPUSD", label: "GBP", color: "#fb7185", hex: 0xfb7185 },
];

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

function stateTone(state: string): string {
  if (state === "CONFIRMED") return "text-[#22c55e]";
  if (state === "ARMED") return "text-[#f59e0b]";
  if (state === "REJECTED" || state === "INVALIDATED") return "text-[#ef4444]";
  if (state === "INSUFFICIENT_DATA") return "text-[#71809a]";
  return "text-[#c9d4e3]";
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
  // A handful of static ambient dots for texture — no per-frame JS, just staggered CSS delays.
  const dust = [
    { x: 18, y: 14, r: 0.35, d: "0s" }, { x: 82, y: 18, r: 0.3, d: "0.6s" },
    { x: 12, y: 46, r: 0.28, d: "1.1s" }, { x: 88, y: 44, r: 0.32, d: "1.8s" },
    { x: 24, y: 8, r: 0.25, d: "2.3s" }, { x: 76, y: 55, r: 0.3, d: "0.3s" },
    { x: 8, y: 30, r: 0.22, d: "1.5s" }, { x: 92, y: 30, r: 0.26, d: "2.6s" },
  ];
  return (
    <svg viewBox="0 0 100 62" className="w-full h-[calc(100%-28px)] relative" preserveAspectRatio="xMidYMid meet">
      <defs>
        <filter id="orion-glow-soft" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="1.4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="orion-glow-strong" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="2.6" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <radialGradient id="orion-core-grad" cx="50%" cy="45%" r="60%">
          <stop offset="0%" stopColor="#3a1014" />
          <stop offset="100%" stopColor="#10161f" />
        </radialGradient>
      </defs>

      {/* ambient dust, decorative only */}
      <g className="orion-dust" opacity={0.6}>
        {dust.map((d, i) => (
          <circle key={i} cx={d.x} cy={d.y} r={d.r} fill="#38bdf8" style={{ animationDelay: d.d }} />
        ))}
      </g>

      {/* connection lines: soft base + animated energy flow when active */}
      {pos.map((p) => (
        <g key={`ln-${p.name}`}>
          <line x1={cx} y1={cy * 0.98} x2={p.x} y2={p.y * 0.98}
            stroke={active.has(p.name) ? "#38bdf8" : "#1e2936"}
            strokeWidth={active.has(p.name) ? 0.5 : 0.22}
            opacity={active.has(p.name) ? 0.55 : 1}
            filter={active.has(p.name) ? "url(#orion-glow-soft)" : undefined} />
          {active.has(p.name) && (
            <line x1={cx} y1={cy * 0.98} x2={p.x} y2={p.y * 0.98}
              stroke="#7dd3fc" strokeWidth={0.35} className="orion-flow-active" />
          )}
        </g>
      ))}

      {/* orbit rings — slow independent rotation, pure CSS transform */}
      <ellipse className="orion-orbit-ring" cx={cx} cy={cy} rx={rx} ry={ry} fill="none"
        stroke="#16202e" strokeWidth={0.3} strokeDasharray="1.5 1.5" />
      <ellipse className="orion-orbit-ring-reverse" cx={cx} cy={cy} rx={rx * 0.72} ry={ry * 0.72}
        fill="none" stroke="#1a2636" strokeWidth={0.3} strokeDasharray="0.6 1.4" />

      {/* central node — layered glow, bioluminescent core */}
      <circle cx={cx} cy={cy} r={11} fill="#ef4444" opacity={thinking ? 0.16 : 0.08}
        filter="url(#orion-glow-strong)" className={thinking ? "orion-pulse" : undefined} />
      <circle cx={cx} cy={cy} r={7.2} fill="url(#orion-core-grad)" stroke="#ef4444" strokeWidth={0.5}
        filter="url(#orion-glow-soft)" className={thinking ? "orion-pulse" : ""} />
      <text x={cx} y={cy - 0.4} textAnchor="middle" fontSize={2.6} fill="#ffffff" fontWeight={700} letterSpacing={0.35}>
        ORION
      </text>
      <text x={cx} y={cy + 2.6} textAnchor="middle" fontSize={1.9} fill={thinking ? "#38bdf8" : "#71809a"}>
        {thinking ? "THINKING" : "CIO"}
      </text>

      {/* agent nodes */}
      {pos.map((p) => (
        <g key={p.name} className={active.has(p.name) ? "orion-node-active" : undefined}>
          {active.has(p.name) && (
            <circle cx={p.x} cy={p.y} r={5.2} fill="#22c55e" opacity={0.18} filter="url(#orion-glow-soft)" />
          )}
          <circle cx={p.x} cy={p.y} r={3.4} fill="#141c28"
            stroke={active.has(p.name) ? "#22c55e" : "#2a3a52"} strokeWidth={0.35}
            filter={active.has(p.name) ? "url(#orion-glow-soft)" : undefined} />
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
