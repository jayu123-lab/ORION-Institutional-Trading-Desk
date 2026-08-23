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
  command_center: { es: "CENTRO DE MANDO", en: "COMMAND CENTER" },
  institutional_desk: { es: "MESA INSTITUCIONAL", en: "INSTITUTIONAL DESK" },
  analyze_gold: { es: "ANALIZAR ORO", en: "ANALYZE GOLD" },
  analyze_xrp: { es: "ANALIZAR XRP", en: "ANALIZAR XRP" },
  analyze_nasdaq: { es: "ANALIZAR NASDAQ", en: "ANALYZE NASDAQ" },
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
