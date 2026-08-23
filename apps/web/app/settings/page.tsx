"use client";

// ORION SETTINGS — connections & credentials.
// Rewritten from scratch: the previous version imported a component kit
// (@/components/ui/*) that does not exist anywhere in this repo and had a
// broken `useState` call, so it never compiled. This version uses the same
// plain-Tailwind terminal style as the rest of the dashboard (see AppShell,
// command/page.tsx) and talks to real backend endpoints only.

import { FormEvent, useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";

type PolymarketStatus = {
  connection: string;
  authentication: string;
  mode: string;
  live_trading: string;
  market_ws: string;
  cob: string;
  gamma: string;
};

type FaroStatus = {
  configured: boolean;
  fingerprint: string | null;
  endpoint_configured: boolean;
  endpoint_url: string;
  auto_send: boolean;
  min_message_length: number;
  last_signal: FaroOutboxEntry | null;
};

type FaroOutboxEntry = {
  status: "SENT" | "DEMO_LOGGED" | "FAILED" | "SKIPPED";
  detail: string;
  message: string;
  ts: string;
};

type Toast = { kind: "ok" | "error"; text: string } | null;

const TABS = [
  { key: "polymarket", label: "CONEXIONES" },
  { key: "faro", label: "FARO" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function SettingsPage() {
  const [tab, setTab] = useState<TabKey>("polymarket");
  const [toast, setToast] = useState<Toast>(null);

  function notify(kind: "ok" | "error", text: string) {
    setToast({ kind, text });
    setTimeout(() => setToast(null), 4000);
  }

  return (
    <div className="flex flex-col gap-3 max-w-3xl">
      <header className="panel px-3 py-2">
        <h1 className="text-[13px] font-bold tracking-widest text-[#c9d4e3]">SETTINGS</h1>
        <p className="text-[10px] text-[#71809a] mt-0.5">
          Conexiones y credenciales. Los secretos nunca se muestran en texto plano — solo huella
          (fingerprint) o estado CONFIGURADO.
        </p>
      </header>

      <nav className="flex gap-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 text-[10px] tracking-wider rounded border transition-colors ${
              tab === t.key
                ? "bg-[#142b3b] text-[#38bdf8] border-[#38bdf8]/60"
                : "text-[#9db2d0] border-[#1e2936] hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === "polymarket" && <PolymarketPanel notify={notify} />}
      {tab === "faro" && <FaroPanel notify={notify} />}

      {toast && (
        <div
          className={`fixed bottom-3 right-3 z-50 panel px-3 py-2 text-[11px] ${
            toast.kind === "ok" ? "border-[#22c55e]/60 text-[#22c55e]" : "border-[#ef4444]/60 text-[#ef4444]"
          }`}
        >
          {toast.text}
        </div>
      )}
    </div>
  );
}

/* ============================================================= Polymarket */

function PolymarketPanel({ notify }: { notify: (k: "ok" | "error", t: string) => void }) {
  const [status, setStatus] = useState<PolymarketStatus | null>(null);
  const [gammaKey, setGammaKey] = useState("");
  const [clobToken, setClobToken] = useState("");
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const res = await apiGet<{ polymarket: PolymarketStatus }>(
        "/api/v1/settings/connections/polymarket/status"
      );
      setStatus(res.polymarket);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "API offline");
    }
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    if (!gammaKey && !clobToken) {
      notify("error", "Introduce al menos una credencial antes de guardar.");
      return;
    }
    setSaving(true);
    try {
      await apiPost("/api/v1/settings/connections/polymarket/configure", {
        gamma_api_key: gammaKey || undefined,
        clob_token: clobToken || undefined,
      });
      setGammaKey("");
      setClobToken("");
      notify("ok", "Credenciales de Polymarket guardadas.");
      await load();
    } catch (e) {
      notify("error", e instanceof Error ? e.message : "Error al guardar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel p-3 flex flex-col gap-3">
      <div className="panel-title !px-0 !pt-0">Polymarket</div>

      {loadError && <p className="text-[10px] text-[#f59e0b]">⚠ {loadError} — mostrando último estado conocido.</p>}

      {status && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1.5 text-[10px]">
          <StatusRow label="Conexión" value={status.connection} />
          <StatusRow label="Autenticación" value={status.authentication} />
          <StatusRow label="Modo" value={status.mode} tone={status.mode === "LIVE" ? "amber" : "green"} />
          <StatusRow label="Live trading" value={status.live_trading} tone={status.live_trading === "ENABLED" ? "red" : "green"} />
          <StatusRow label="Gamma" value={status.gamma} />
          <StatusRow label="CLOB" value={status.cob} />
        </div>
      )}

      <form onSubmit={onSave} className="flex flex-col gap-2 border-t border-[#1e2936] pt-3">
        <Field
          label="API Key Gamma"
          hint="Opcional — descubrimiento de mercados"
          value={gammaKey}
          onChange={setGammaKey}
          placeholder="gamma_api_key"
        />
        <Field
          label="CLOB Token"
          hint="Necesario para autenticar operaciones (Fase 5, aún bloqueada)"
          value={clobToken}
          onChange={setClobToken}
          placeholder="clob_token"
        />
        <button
          type="submit"
          disabled={saving}
          className="self-start mt-1 rounded border border-[#38bdf8]/60 px-3 py-1.5 text-[10px] text-[#38bdf8]
                     hover:bg-[#142b3b] disabled:opacity-50"
        >
          {saving ? "GUARDANDO…" : "GUARDAR"}
        </button>
      </form>
    </section>
  );
}

/* ==================================================================== Faro */

function FaroPanel({ notify }: { notify: (k: "ok" | "error", t: string) => void }) {
  const [status, setStatus] = useState<FaroStatus | null>(null);
  const [history, setHistory] = useState<FaroOutboxEntry[]>([]);
  const [apiKey, setApiKey] = useState("");
  const [endpointUrl, setEndpointUrl] = useState("");
  const [autoSend, setAutoSend] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const res = await apiGet<{ faro: FaroStatus }>("/api/v1/settings/connections/faro/status");
      setStatus(res.faro);
      setEndpointUrl(res.faro.endpoint_url);
      setAutoSend(res.faro.auto_send);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "API offline");
    }
    try {
      const h = await apiGet<{ history: FaroOutboxEntry[] }>(
        "/api/v1/settings/connections/faro/history?limit=10"
      );
      setHistory(h.history);
    } catch {
      /* history is best-effort */
    }
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await apiPost("/api/v1/settings/connections/faro/configure", {
        api_key: apiKey || undefined,
        endpoint_url: endpointUrl,
        auto_send: autoSend,
      });
      setApiKey("");
      notify("ok", "Configuración de Faro guardada.");
      await load();
    } catch (e) {
      notify("error", e instanceof Error ? e.message : "Error al guardar.");
    } finally {
      setSaving(false);
    }
  }

  async function onRemove() {
    try {
      await apiPost("/api/v1/settings/connections/faro/remove", {});
      notify("ok", "API Key de Faro eliminada.");
      await load();
    } catch (e) {
      notify("error", e instanceof Error ? e.message : "Error al eliminar.");
    }
  }

  async function onTest() {
    setTesting(true);
    try {
      const res = await apiPost<FaroOutboxEntry>("/api/v1/settings/connections/faro/test", {});
      notify(
        res.status === "FAILED" ? "error" : "ok",
        `Señal de prueba: ${res.status} — ${res.detail}`
      );
      await load();
    } catch (e) {
      notify("error", e instanceof Error ? e.message : "Error al enviar prueba.");
    } finally {
      setTesting(false);
    }
  }

  return (
    <section className="panel p-3 flex flex-col gap-3">
      <div className="panel-title !px-0 !pt-0">Faro — envío de señales</div>
      <p className="text-[10px] text-[#71809a]">
        Cada señal enviada incluye ticker, entrada, SL, TP y R:R, y tiene al menos{" "}
        {status?.min_message_length ?? 200} caracteres. Se dispara automáticamente cuando el Risk
        Manager aprueba una idea (sin reducir tamaño).
      </p>

      {loadError && <p className="text-[10px] text-[#f59e0b]">⚠ {loadError}</p>}

      {status && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1.5 text-[10px]">
          <StatusRow label="API Key" value={status.configured ? status.fingerprint ?? "CONFIGURADA" : "NO CONFIGURADA"}
            tone={status.configured ? "green" : "amber"} />
          <StatusRow label="Endpoint" value={status.endpoint_configured ? "CONFIGURADO" : "PENDIENTE (DEMO)"}
            tone={status.endpoint_configured ? "green" : "amber"} />
          <StatusRow label="Envío automático" value={status.auto_send ? "ACTIVADO" : "DESACTIVADO"}
            tone={status.auto_send ? "green" : "default"} />
          <StatusRow label="Última señal" value={status.last_signal ? status.last_signal.status : "—"}
            tone={status.last_signal?.status === "SENT" ? "green" : status.last_signal?.status === "FAILED" ? "red" : "default"} />
        </div>
      )}

      {!status?.endpoint_configured && (
        <p className="text-[10px] text-[#38bdf8] border border-[#38bdf8]/30 rounded px-2 py-1.5 bg-[#0d1b26]">
          Sin endpoint real de Faro todavía: las señales aprobadas se componen y quedan registradas
          localmente (DEMO_LOGGED), pero no se envían por red. En cuanto tengas la URL de la API de
          Faro, pégala abajo y el envío pasa a ser real sin más cambios.
        </p>
      )}

      <form onSubmit={onSave} className="flex flex-col gap-2 border-t border-[#1e2936] pt-3">
        <Field
          label="API Key de Faro"
          hint="Se guarda de forma segura — nunca se muestra en texto plano de nuevo"
          value={apiKey}
          onChange={setApiKey}
          placeholder={status?.configured ? "•••• (ya configurada — deja vacío para no cambiarla)" : "sk-faro-…"}
        />
        <Field
          label="Endpoint de Faro"
          hint="URL a la que se envía cada señal (déjalo vacío para modo DEMO)"
          value={endpointUrl}
          onChange={setEndpointUrl}
          placeholder="https://api.faro.example/v1/signals"
        />
        <label className="flex items-center gap-2 text-[10px] text-[#9db2d0]">
          <input type="checkbox" checked={autoSend} onChange={(e) => setAutoSend(e.target.checked)} />
          Enviar automáticamente cuando Risk apruebe una idea (sin reducir tamaño)
        </label>
        <div className="flex gap-2 mt-1">
          <button
            type="submit"
            disabled={saving}
            className="rounded border border-[#38bdf8]/60 px-3 py-1.5 text-[10px] text-[#38bdf8]
                       hover:bg-[#142b3b] disabled:opacity-50"
          >
            {saving ? "GUARDANDO…" : "GUARDAR"}
          </button>
          <button
            type="button"
            onClick={onTest}
            disabled={testing}
            className="rounded border border-[#22c55e]/60 px-3 py-1.5 text-[10px] text-[#22c55e]
                       hover:bg-[#0f2417] disabled:opacity-50"
          >
            {testing ? "ENVIANDO…" : "ENVIAR SEÑAL DE PRUEBA"}
          </button>
          {status?.configured && (
            <button
              type="button"
              onClick={onRemove}
              className="rounded border border-[#ef4444]/60 px-3 py-1.5 text-[10px] text-[#ef4444] hover:bg-[#29171b]"
            >
              ELIMINAR API KEY
            </button>
          )}
        </div>
      </form>

      <div className="border-t border-[#1e2936] pt-3">
        <p className="text-[9px] tracking-[0.14em] text-[#5b6b85] mb-1.5">HISTORIAL RECIENTE</p>
        {history.length === 0 && <p className="text-[10px] text-[#71809a]">Sin señales enviadas aún.</p>}
        <ul className="space-y-1.5 max-h-64 overflow-y-auto">
          {history.map((h, i) => (
            <li key={i} className="text-[10px] border border-[#1e2936] rounded px-2 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span
                  className={
                    h.status === "SENT" ? "text-[#22c55e]"
                      : h.status === "FAILED" ? "text-[#ef4444]"
                        : h.status === "DEMO_LOGGED" ? "text-[#38bdf8]" : "text-[#71809a]"
                  }
                >
                  {h.status}
                </span>
                <span className="text-[#71809a]">{fmtTs(h.ts)}</span>
              </div>
              <p className="text-[#71809a] mt-0.5">{h.detail}</p>
              <details className="mt-1">
                <summary className="cursor-pointer text-[9px] text-[#71809a] hover:text-white select-none">
                  ver mensaje
                </summary>
                <pre className="whitespace-pre-wrap text-[9px] text-[#c9d4e3] mt-1 border-l border-[#1e2936] pl-2">
                  {h.message}
                </pre>
              </details>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/* =============================================================== pieces */

function Field({
  label, hint, value, onChange, placeholder,
}: { label: string; hint?: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-medium text-[#cbd5e1]">
        {label}
        {hint && <span className="ml-1.5 text-[9px] font-normal text-[#71809a]">{hint}</span>}
      </span>
      <input
        type="password"
        autoComplete="off"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="bg-[#10161f] border border-[#1e2936] rounded px-2.5 py-1.5 text-[11px]
                   outline-none focus:border-[#38bdf8]"
      />
    </label>
  );
}

function StatusRow({ label, value, tone = "default" }: {
  label: string; value: string; tone?: "default" | "green" | "red" | "amber";
}) {
  const color = tone === "green" ? "text-[#22c55e]" : tone === "red" ? "text-[#ef4444]"
    : tone === "amber" ? "text-[#f59e0b]" : "text-[#c9d4e3]";
  return (
    <span className="flex gap-1.5 items-baseline">
      <span className="text-[#71809a]">{label}</span>
      <span className={color}>{value}</span>
    </span>
  );
}

function fmtTs(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}
