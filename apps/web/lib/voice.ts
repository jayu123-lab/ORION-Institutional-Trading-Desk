"use client";

// ORION voice announcer (P38, P39) — speaks short alerts in the language
// currently selected in the UI (see LanguageMenu / useLanguage).
//
// Two engines, zero setup required:
//  - Browser (default): the OS/browser's own free SpeechSynthesis voice.
//    No API key, no network cost, works immediately.
//  - OpenAI TTS (optional upgrade): once the user configures an OpenAI API
//    key in Settings > Voz IA, `/api/v1/voice/speak` synthesizes the same
//    text with a much more natural voice instead — at the user's own OpenAI
//    cost. Every call falls back to the browser voice automatically on any
//    failure (not configured, offline, quota, bad key…), so this can never
//    leave the user without alerts.
// Must never throw or block the app — every entry point below fails silently.

import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/api";
import type { LangCode } from "@/lib/i18n";

const STORAGE_KEY = "orion_voice_enabled";
const ENGINE_POLL_MS = 30_000;

// BCP-47 locale ORION asks the browser for, per UI language. Full ORION
// phrase templates only exist for es/en (see phrase builders below); the
// other UI languages still get a matching accent from the browser, but the
// spoken sentence itself falls back to English.
const VOICE_LOCALE: Record<LangCode, string> = {
  es: "es-ES",
  en: "en-US",
  fr: "fr-FR",
  de: "de-DE",
  it: "it-IT",
  pt: "pt-PT",
};

// Friendlier spoken names for the 4 priority assets instead of raw tickers.
const ASSET_NAME: Record<string, { es: string; en: string }> = {
  XAUUSD: { es: "el oro", en: "gold" },
  NQ: { es: "el Nasdaq", en: "the Nasdaq" },
  EURUSD: { es: "el euro dólar", en: "euro dollar" },
  GBPUSD: { es: "la libra dólar", en: "pound dollar" },
};

function spokenAsset(symbol: string, lang: LangCode): string {
  const entry = ASSET_NAME[symbol];
  if (!entry) return symbol;
  return lang === "es" ? entry.es : entry.en;
}

function pickVoice(voices: SpeechSynthesisVoice[], locale: string): SpeechSynthesisVoice | undefined {
  const prefix = locale.split("-")[0];
  return voices.find((v) => v.lang === locale) ?? voices.find((v) => v.lang.toLowerCase().startsWith(prefix));
}

/**
 * Core announcer: owns the enabled/disabled toggle (persisted per-browser in
 * localStorage — this never touches the backend or leaves the device), polls
 * whether an OpenAI voice is configured, and exposes a single `announce(text)`
 * entry point that queues phrases so bursts read out in order instead of
 * cutting each other off. `setEnabled(true)` always confirms with the free
 * browser voice on the same click that flips the toggle (instant, and
 * browsers are far more willing to grant audio inside a direct user gesture).
 */
export function useVoiceAnnouncer(lang: LangCode) {
  const [enabled, setEnabledState] = useState(false);
  const [supported, setSupported] = useState(false);
  const [openaiReady, setOpenaiReady] = useState(false);
  const voicesRef = useRef<SpeechSynthesisVoice[]>([]);
  const openaiReadyRef = useRef(false);
  const queueRef = useRef<string[]>([]);
  const playingRef = useRef(false);
  const langRef = useRef(lang);
  langRef.current = lang;

  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      setSupported(false);
      return;
    }
    setSupported(true);
    try {
      if (window.localStorage.getItem(STORAGE_KEY) === "1") setEnabledState(true);
    } catch {
      /* private mode etc. — stays off by default */
    }
    const loadVoices = () => {
      voicesRef.current = window.speechSynthesis.getVoices();
    };
    loadVoices();
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", loadVoices);
  }, []);

  // poll whether an OpenAI voice key is configured (Settings > Voz IA) —
  // upgrades/downgrades the engine automatically without needing a page reload
  useEffect(() => {
    if (typeof window === "undefined") return;
    let cancelled = false;
    const check = () => {
      fetch(`${API_URL}/api/v1/settings/connections/voice/status`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (cancelled) return;
          const ready = !!d?.voice?.configured;
          openaiReadyRef.current = ready;
          setOpenaiReady(ready);
        })
        .catch(() => undefined);
    };
    check();
    const id = setInterval(check, ENGINE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const speakBrowser = useCallback((text: string): Promise<void> => {
    return new Promise((resolve) => {
      if (typeof window === "undefined" || !("speechSynthesis" in window)) {
        resolve();
        return;
      }
      const locale = VOICE_LOCALE[langRef.current] ?? "en-US";
      const u = new SpeechSynthesisUtterance(text);
      u.lang = locale;
      u.rate = 1.0;
      const v = pickVoice(voicesRef.current, locale);
      if (v) u.voice = v;
      u.onend = () => resolve();
      u.onerror = () => resolve();
      window.speechSynthesis.speak(u);
    });
  }, []);

  const speakOpenAI = useCallback(async (text: string): Promise<boolean> => {
    try {
      const res = await fetch(`${API_URL}/api/v1/voice/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang: langRef.current }),
      });
      if (!res.ok) return false;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      await new Promise<void>((resolve) => {
        const audio = new Audio(url);
        audio.onended = () => resolve();
        audio.onerror = () => resolve();
        audio.play().catch(() => resolve());
      });
      URL.revokeObjectURL(url);
      return true;
    } catch {
      return false;
    }
  }, []);

  const processQueue = useCallback(async () => {
    if (playingRef.current) return;
    const next = queueRef.current.shift();
    if (next === undefined) return;
    playingRef.current = true;
    const openaiWorked = openaiReadyRef.current ? await speakOpenAI(next) : false;
    if (!openaiWorked) await speakBrowser(next);
    playingRef.current = false;
    void processQueue();
  }, [speakBrowser, speakOpenAI]);

  const setEnabled = useCallback(
    (next: boolean) => {
      setEnabledState(next);
      try {
        window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      if (!supported) return;
      window.speechSynthesis.cancel();
      queueRef.current = [];
      if (next) void speakBrowser(langRef.current === "es" ? "Voz de ORION activada." : "ORION voice enabled.");
    },
    [supported, speakBrowser],
  );

  const announce = useCallback(
    (text: string) => {
      if (!enabled || typeof window === "undefined") return;
      queueRef.current.push(text);
      void processQueue();
    },
    [enabled, processQueue],
  );

  return { enabled, setEnabled, announce, supported, openaiReady };
}

/* =============================================== market-event phrase builders */

type TickerLike = { symbol: string; price: number | null; change_pct: number | null; status: string };
type OpportunityLike = { setup_id: string; symbol: string; setup: string; state: string };
type IntelLike = {
  risk_warnings: { message: string; severity: string }[];
  latest_news: { title: string; source: string | null; relevance: string | null }[];
  cio_decision: { asset: string | null; stance: string | null; summary: string | null };
} | null;

const PRICE_MOVE_THRESHOLD_PCT = 0.4; // ignore noise below this
const COOLDOWN_MS = 3 * 60_000; // per alert key, so a hovering price/setup doesn't spam

function phraseMove(symbol: string, changePct: number, lang: LangCode): string {
  const asset = spokenAsset(symbol, lang);
  const up = changePct >= 0;
  return lang === "es"
    ? `Atención. Pon la vista en ${asset}. Posible ${up ? "subida" : "bajada"} de ${Math.abs(changePct).toFixed(2)} por ciento.`
    : `Attention. Keep an eye on ${asset}. Possible ${up ? "upward move" : "downward move"} of ${Math.abs(changePct).toFixed(2)} percent.`;
}

function phraseLiquidity(symbol: string, lang: LangCode): string {
  const asset = spokenAsset(symbol, lang);
  return lang === "es" ? `Posible liquidación en ${asset}.` : `Possible liquidity sweep on ${asset}.`;
}

function phraseOpportunity(symbol: string, setup: string, lang: LangCode): string {
  const asset = spokenAsset(symbol, lang);
  return lang === "es"
    ? `Nueva oportunidad detectada en ${asset}: ${setup}.`
    : `New opportunity detected on ${asset}: ${setup}.`;
}

function phraseCioDecision(asset: string | null, stance: string | null, lang: LangCode): string {
  const a = asset ? spokenAsset(asset, lang) : lang === "es" ? "el mercado" : "the market";
  return lang === "es"
    ? `ORION C I O decide ${stance ?? "sin decisión"} en ${a}.`
    : `ORION C I O decision: ${stance ?? "no decision"} on ${a}.`;
}

function phraseRisk(message: string, lang: LangCode): string {
  return lang === "es" ? `Alerta de riesgo: ${message}.` : `Risk alert: ${message}.`;
}

function phraseNews(title: string, lang: LangCode): string {
  return lang === "es" ? `Noticia de alto impacto: ${title}.` : `High impact news: ${title}.`;
}

/* ============================================== interactive CIO narration */
// P40: "voz interactiva" — after every CIO reply, speak what the desk
// actually concluded. Parses the REAL structured text ORION CIO already
// generates (core/desk/cio.py: "INFERENCES (per specialist):" block + the
// closing "En cristiano: ..." line) — nothing here is invented, it is the
// same data already shown in the terminal, just read aloud. Always parses
// the raw (pre-translation) English-labelled reply so the extraction is
// reliable regardless of the UI language / auto-translate state.

const AGENT_SPOKEN_ES: Record<string, string> = {
  "orion-macro": "Macro", "orion-metals": "Metales", "orion-forex": "Forex",
  "orion-crypto": "Cripto", "orion-equities": "Acciones",
  "orion-liquidity": "Liquidez", "orion-positioning": "Posicionamiento",
  "orion-crossasset": "Cross-asset", "orion-news": "Noticias",
  "orion-quant": "Cuantitativo", "orion-risk": "Riesgo", "orion-audit": "Auditoría",
};
const AGENT_SPOKEN_EN: Record<string, string> = {
  "orion-macro": "Macro", "orion-metals": "Metals", "orion-forex": "Forex",
  "orion-crypto": "Crypto", "orion-equities": "Equities",
  "orion-liquidity": "Liquidity", "orion-positioning": "Positioning",
  "orion-crossasset": "Cross-asset", "orion-news": "News",
  "orion-quant": "Quant", "orion-risk": "Risk", "orion-audit": "Audit",
};

function humanizeAgentId(agent: string): string {
  return agent.replace(/^orion-/, "").replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const STANCE_ES: Record<string, string> = {
  LONG: "sesgo comprador", SHORT: "sesgo vendedor",
  WAIT: "en espera", NEUTRAL: "sin sesgo claro",
};
const STANCE_EN: Record<string, string> = {
  LONG: "bullish bias", SHORT: "bearish bias",
  WAIT: "waiting", NEUTRAL: "no clear bias",
};
const CONFIDENCE_ES: Record<string, string> = { HIGH: "alta", MODERATE: "moderada", LOW: "baja" };
const CONFIDENCE_EN: Record<string, string> = { HIGH: "high", MODERATE: "moderate", LOW: "low" };

type SpecialistLine = { agent: string; stance: string; confidence: string; summary: string };

function parseSpecialistLines(reply: string): SpecialistLine[] {
  const lines = reply.split("\n");
  const startIdx = lines.findIndex((l) => l.trim() === "INFERENCES (per specialist):");
  if (startIdx === -1) return [];
  const out: SpecialistLine[] = [];
  for (let i = startIdx + 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === "") break; // block ends at the first blank line
    const m = line.match(/^-\s+([\w-]+):\s+([A-Z]+)\s+·\s+([A-Z]+)\s+—\s+(.+)$/);
    if (m) out.push({ agent: m[1], stance: m[2], confidence: m[3], summary: m[4] });
  }
  return out;
}

function parseNaturalLine(reply: string): string | null {
  const line = reply.split("\n").find((l) => l.trim().startsWith("En cristiano:"));
  return line ? line.trim() : null;
}

/**
 * Builds the spoken phrases for one CIO reply: the natural-language "En
 * cristiano" closing line (already native Spanish — read as-is when the UI
 * is in Spanish), followed by up to `maxSpecialists` short per-specialist
 * lines built from the real stance/confidence/summary the desk computed.
 * Pure function — easy to unit-test, no side effects.
 */
export function buildCioNarrationPhrases(
  reply: string,
  lang: LangCode,
  maxSpecialists = 3,
): string[] {
  if (!reply) return [];
  const phrases: string[] = [];
  if (lang === "es") {
    const natural = parseNaturalLine(reply);
    if (natural) phrases.push(natural.replace(/^En cristiano:\s*/, "Resumen de la mesa: "));
  }
  const stanceMap = lang === "es" ? STANCE_ES : STANCE_EN;
  const confMap = lang === "es" ? CONFIDENCE_ES : CONFIDENCE_EN;
  const agentMap = lang === "es" ? AGENT_SPOKEN_ES : AGENT_SPOKEN_EN;
  const specialists = parseSpecialistLines(reply).slice(0, maxSpecialists);
  for (const s of specialists) {
    const name = agentMap[s.agent] ?? humanizeAgentId(s.agent);
    const stance = stanceMap[s.stance] ?? s.stance;
    const conf = confMap[s.confidence] ?? s.confidence;
    phrases.push(
      lang === "es"
        ? `${name}: ${stance}, confianza ${conf}.`
        : `${name}: ${stance}, ${conf} confidence.`,
    );
  }
  return phrases;
}

/**
 * Watches the Command Center's already-polled state (ticker/radar/intel —
 * no extra network calls of its own) and calls `announce()` on meaningful
 * changes: relevant price moves, newly-armed radar setups, new high-severity
 * risk warnings / high-impact news, and CIO decision changes. Everything is
 * scoped to `prioritySymbols` (XAUUSD/NQ/EURUSD/GBPUSD today) so it doesn't
 * drown the user in chatter about assets they didn't ask to be watched over.
 */
export function useMarketVoiceAlerts(params: {
  lang: LangCode;
  enabled: boolean;
  announce: (text: string) => void;
  ticker: TickerLike[];
  radar: OpportunityLike[];
  intel: IntelLike;
  prioritySymbols: Set<string>;
}) {
  const { lang, enabled, announce, ticker, radar, intel, prioritySymbols } = params;
  const lastFiredAt = useRef<Record<string, number>>({});
  const seenRisk = useRef<Set<string>>(new Set());
  const seenNews = useRef<Set<string>>(new Set());
  const lastCioKey = useRef<string | null>(null);

  const canFire = useCallback((key: string) => {
    const now = Date.now();
    const last = lastFiredAt.current[key] ?? 0;
    if (now - last < COOLDOWN_MS) return false;
    lastFiredAt.current[key] = now;
    return true;
  }, []);

  // price moves on priority assets
  useEffect(() => {
    if (!enabled) return;
    for (const row of ticker) {
      if (!prioritySymbols.has(row.symbol) || row.change_pct == null) continue;
      if (Math.abs(row.change_pct) < PRICE_MOVE_THRESHOLD_PCT) continue;
      const key = `move:${row.symbol}:${row.change_pct >= 0 ? "up" : "down"}`;
      if (!canFire(key)) continue;
      announce(phraseMove(row.symbol, row.change_pct, lang));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, enabled, lang, prioritySymbols]);

  // newly-armed radar setups on priority assets
  useEffect(() => {
    if (!enabled) return;
    for (const op of radar) {
      if (op.state !== "ARMED" || !prioritySymbols.has(op.symbol)) continue;
      const key = `armed:${op.symbol}:${op.setup}`;
      if (!canFire(key)) continue;
      if (op.setup.toUpperCase().includes("LIQUIDITY")) {
        announce(phraseLiquidity(op.symbol, lang));
      } else {
        announce(phraseOpportunity(op.symbol, op.setup, lang));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [radar, enabled, lang, prioritySymbols]);

  // risk warnings, high-impact news, CIO decision changes
  useEffect(() => {
    if (!enabled || !intel) return;
    for (const w of intel.risk_warnings) {
      const key = `risk:${w.message}`;
      if (seenRisk.current.has(key)) continue;
      seenRisk.current.add(key);
      announce(phraseRisk(w.message, lang));
    }
    for (const n of intel.latest_news) {
      if (n.relevance !== "HIGH") continue;
      const key = `news:${n.title}`;
      if (seenNews.current.has(key)) continue;
      seenNews.current.add(key);
      announce(phraseNews(n.title, lang));
    }
    const stance = intel.cio_decision?.stance ?? null;
    if (stance) {
      const cioKey = `${intel.cio_decision?.asset ?? ""}:${stance}`;
      if (lastCioKey.current !== cioKey) {
        lastCioKey.current = cioKey;
        announce(phraseCioDecision(intel.cio_decision?.asset ?? null, stance, lang));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intel, enabled, lang]);
}
