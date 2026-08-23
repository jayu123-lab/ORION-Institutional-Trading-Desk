"use client";

// ORION client-side i18n (P20-P23).
// Catalogs mirror core/translation/service.py; refreshed live from
// /api/v1/i18n/catalogs so new keys/languages need no frontend redeploy.
// Fallback chain: selected lang -> es -> key.

import { useCallback, useEffect, useState } from "react";

export const LANGUAGES = [
  { code: "es", name: "ESPAÑOL" },
  { code: "en", name: "ENGLISH" },
  { code: "fr", name: "FRANÇAIS" },
  { code: "de", name: "DEUTSCH" },
  { code: "it", name: "ITALIANO" },
  { code: "pt", name: "PORTUGUÊS" },
] as const;

export type LangCode = (typeof LANGUAGES)[number]["code"];
export const DEFAULT_LANG: LangCode = "es";

const EMBEDDED_CATALOGS: Record<string, Record<string, string>> = {
  home: { es: "INICIO", en: "HOME", fr: "ACCUEIL", de: "START", it: "HOME", pt: "INÍCIO" },
  command_center: { es: "CENTRO DE MANDO", en: "COMMAND CENTER" },
  market: { es: "MERCADO", en: "MARKET", fr: "MARCHÉ", de: "MARKT", it: "MERCATO", pt: "MERCADO" },
  gold: { es: "ORO", en: "GOLD", fr: "OR", de: "GOLD", it: "ORO", pt: "OURO" },
  crypto: { es: "CRYPTO", en: "CRYPTO" },
  positioning: { es: "POSICIONAMIENTO", en: "POSITIONING" },
  agents: { es: "AGENTES", en: "AGENTS" },
  system: { es: "SISTEMA", en: "SYSTEM" },
  settings: { es: "AJUSTES", en: "SETTINGS", fr: "PARAMÈTRES", de: "EINSTELLUNGEN", it: "IMPOSTAZIONI", pt: "CONFIGURAÇÕES" },
  session: { es: "SESIÓN", en: "SESSION" },
  regime: { es: "RÉGIMEN", en: "REGIME" },
  bias_score: { es: "PUNTUACIÓN DE SESGO", en: "BIAS SCORE" },
  trade_quality: { es: "CALIDAD DE OPERACIÓN", en: "TRADE QUALITY" },
  decision: { es: "DECISIÓN", en: "DECISION" },
  macro_flag: { es: "AVISO MACRO", en: "MACRO FLAG" },
  news: { es: "NOTICIAS", en: "NEWS" },
  liquidity_event: { es: "EVENTO DE LIQUIDEZ", en: "LIQUIDITY EVENT" },
  risk_warning: { es: "AVISO DE RIESGO", en: "RISK WARNING" },
  last_cio_decision: { es: "ÚLTIMA DECISIÓN DEL CIO", en: "LAST CIO DECISION" },
  timeline: { es: "CRONOLOGÍA", en: "TIMELINE" },
  institutional_desk: { es: "MESA INSTITUCIONAL", en: "INSTITUTIONAL DESK" },
  analyze_gold: { es: "ANALIZAR ORO", en: "ANALYZE GOLD" },
  analyze_xrp: { es: "ANALIZAR XRP", en: "ANALIZAR XRP" },
  analyze_nasdaq: { es: "ANALIZAR NASDAQ", en: "ANALYZE NASDAQ" },
  analyze_forex: { es: "ANALIZAR EURUSD", en: "ANALYZE EURUSD" },
  pre_london: { es: "PRE-LONDRES", en: "PRE-LONDON" },
  pre_ny: { es: "PRE-NUEVA YORK", en: "PRE-NY" },
  convene_desk: { es: "CONVOCAR MESA", en: "CONVENE DESK" },
  risk_check: { es: "CHEQUEO DE RIESGO", en: "RISK CHECK" },
  system_status: { es: "ESTADO DEL SISTEMA", en: "SYSTEM STATUS" },
  agent_activity: { es: "ACTIVIDAD DE AGENTES", en: "AGENT ACTIVITY" },
  intelligence: { es: "INTELIGENCIA", en: "INTELLIGENCE" },
  auto_translate: { es: "AUTO TRADUCIR", en: "AUTO TRANSLATE" },
  view_original: { es: "VER ORIGINAL", en: "VIEW ORIGINAL" },
  terminal: { es: "TERMINAL", en: "TERMINAL" },
  send: { es: "ENVIAR", en: "SEND" },
  api_offline: { es: "API FUERA DE SERVICIO", en: "API OFFLINE" },
  feed_degraded: { es: "FEED DEGRADADO", en: "FEED DEGRADED" },
  translator_unavailable: {
    es: "TRADUCTOR NO DISPONIBLE",
    en: "TRANSLATOR UNAVAILABLE",
  },
  ask_cio: { es: "Preguntar a ORION CIO…", en: "Ask ORION CIO…", fr: "Demander à ORION CIO…", de: "ORION CIO fragen…", it: "Chiedi a ORION CIO…", pt: "Perguntar ao ORION CIO…" },
  ask: { es: "PREGUNTAR", en: "ASK", fr: "DEMANDER", de: "FRAGEN", it: "CHIEDI", pt: "PERGUNTAR" },
  talk_to_cio: { es: "HABLAR CON ORION CIO", en: "TALK TO ORION CIO" },
  cio_drawer_hint: { es: "Todo mensaje se envía directamente al CIO. No se ejecutan órdenes.", en: "Every message goes directly to the CIO. No orders are executed." },
  cio_thinking: { es: "ORION CIO está analizando…", en: "ORION CIO is analyzing…" },
  view_full_analysis: { es: "VER ANÁLISIS COMPLETO", en: "VIEW FULL ANALYSIS" },
  enter_command_center: { es: "ENTRAR AL CENTRO DE MANDO", en: "ENTER COMMAND CENTER" },
  system_state: { es: "ESTADO DEL SISTEMA", en: "SYSTEM STATE" },
  database: { es: "BASE DE DATOS", en: "DATABASE" },
  market_feeds: { es: "MERCADO", en: "MARKET FEEDS" },
  cftc: { es: "CFTC", en: "CFTC" },
  risk: { es: "RIESGO", en: "RISK" },
  view_market: { es: "VER MERCADO", en: "VIEW MARKET" },
  view_system: { es: "VER SISTEMA", en: "VIEW SYSTEM" },
  translation_unavailable: { es: "Traducción no disponible — mostrando original", en: "Translation unavailable — showing original" },
};

type Catalogs = Record<string, Record<string, string>>;

const STORAGE_KEY = "orion_ui_language";

export function useLanguage() {
  const [lang, setLangState] = useState<LangCode>(DEFAULT_LANG);
  const [catalogs, setCatalogs] = useState<Catalogs>(EMBEDDED_CATALOGS);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY) as LangCode | null;
      if (stored && LANGUAGES.some((l) => l.code === stored)) {
        setLangState(stored);
      }
    } catch {
      /* private mode etc. — default language is fine */
    }
  }, []);

  const setLang = useCallback((next: LangCode) => {
    setLangState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  const t = useCallback(
    (key: string): string => {
      const entry = catalogs[key];
      if (!entry) return key;
      return entry[lang] ?? entry[DEFAULT_LANG] ?? key;
    },
    [catalogs, lang],
  );

  const applyServerCatalogs = useCallback(
    (payload: { catalogs?: Catalogs }) => {
      if (payload?.catalogs && Object.keys(payload.catalogs).length > 0) {
        setCatalogs({ ...EMBEDDED_CATALOGS, ...payload.catalogs });
      }
    },
    [],
  );

  return { lang, setLang, t, applyServerCatalogs };
}
