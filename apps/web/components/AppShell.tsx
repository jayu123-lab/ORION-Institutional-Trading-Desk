"use client";

import Link from "next/link";
import { FormEvent, ReactNode, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { API_URL } from "@/lib/api";
import { LANGUAGES, LangCode, useLanguage } from "@/lib/i18n";

const NAV = [
  ["home", "/start"], ["command_center", "/command"], ["market", "/"],
  ["gold", "/gold"], ["crypto", "/crypto"], ["positioning", "/positioning"],
  ["agents", "/agents"], ["system", "/status"],
] as const;

const BREADCRUMBS: Record<string, string> = {
  "/start": "home", "/command": "command_center", "/": "market", "/gold": "gold",
  "/crypto": "crypto", "/positioning": "positioning", "/agents": "agents", "/status": "system",
};

type ChatReply = { cio?: { reply?: string } };

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { lang, setLang, t, applyServerCatalogs } = useLanguage();
  const [question, setQuestion] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [sending, setSending] = useState(false);
  const [reply, setReply] = useState<string | null>(null);
  const [original, setOriginal] = useState<string | null>(null);
  const [autoTranslate, setAutoTranslate] = useState(true);
  const [translateWarning, setTranslateWarning] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/api/v1/i18n/catalogs`).then((r) => r.ok ? r.json() : null)
      .then((payload) => payload && applyServerCatalogs(payload)).catch(() => undefined);
  }, [applyServerCatalogs]);

  useEffect(() => {
    const open = () => setDrawer(true);
    window.addEventListener("orion:open-cio", open);
    return () => window.removeEventListener("orion:open-cio", open);
  }, []);

  async function askCio(event?: FormEvent) {
    event?.preventDefault();
    const text = question.trim();
    if (!text || sending) return;
    setSending(true); setDrawer(true); setReply(null); setOriginal(null); setTranslateWarning(false);
    try {
      const response = await fetch(`${API_URL}/api/v1/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text, room: "global-cio" }),
      });
      if (!response.ok) throw new Error(`API ${response.status}`);
      const data = await response.json() as ChatReply;
      const source = data.cio?.reply ?? "ORION CIO no devolvió análisis.";
      let shown = source;
      if (autoTranslate) {
        const tr = await fetch(`${API_URL}/api/v1/i18n/translate`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: source, target_lang: lang }),
        }).then((r) => r.ok ? r.json() : null).catch(() => null);
        if (tr?.translated) shown = tr.text;
        else if (tr && !tr.translated) setTranslateWarning(true);
      }
      setReply(shown); setOriginal(shown === source ? null : source);
    } catch (error) {
      setReply(`CIO no disponible: ${error instanceof Error ? error.message : "error desconocido"}`);
    } finally { setSending(false); }
  }

  const currentLabel = t(BREADCRUMBS[pathname] ?? "system");
  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      <aside className="w-full lg:w-52 shrink-0 border-b lg:border-b-0 lg:border-r border-[#1e2936] bg-[#0d1219] p-3 flex lg:flex-col">
        <div className="mb-2 lg:mb-6 px-2 shrink-0">
          <Link href="/start" className="text-[15px] font-bold tracking-widest text-red-500">ORION</Link>
          <p className="text-[10px] text-[#71809a]">{t("institutional_desk")}</p>
        </div>
        <nav className="flex flex-1 flex-wrap lg:flex-col gap-1 overflow-x-auto">
          {NAV.map(([key, href]) => (
            <Link key={href} href={href} aria-current={pathname === href ? "page" : undefined}
              className={`rounded px-3 py-1.5 text-[11px] tracking-wider transition-colors ${pathname === href
                ? "bg-[#142b3b] text-[#38bdf8] border-l-2 border-[#38bdf8]"
                : "text-[#c9d4e3]/80 hover:bg-[#141c28] hover:text-white"}`}>
              {t(key)}
            </Link>
          ))}
        </nav>
        <div className="hidden lg:block mt-auto pt-8 text-[10px] leading-relaxed text-[#71809a] px-2">
          PAPER MODE ONLY<br />LIVE DISABLED
        </div>
      </aside>
      <main className="flex-1 min-w-0 overflow-x-hidden p-3 sm:p-4">
        <header className="mb-3 flex flex-wrap items-center gap-2 border-b border-[#1e2936] pb-2">
          <Link href="/start" className="text-[10px] text-[#38bdf8] hover:text-white">ORION</Link>
          <span className="text-[10px] text-[#71809a]">&gt;</span>
          <span className="text-[10px] tracking-wider text-[#c9d4e3]">{currentLabel}</span>
          <form onSubmit={askCio} className="order-last w-full sm:order-none sm:ml-auto sm:w-auto flex min-w-0 flex-1 sm:max-w-md gap-1">
            <input value={question} onChange={(e) => setQuestion(e.target.value)}
              placeholder={t("ask_cio")} aria-label={t("ask_cio")}
              className="min-w-0 flex-1 rounded border border-[#1e2936] bg-[#10161f] px-2 py-1 text-[10px] outline-none focus:border-[#38bdf8]" />
            <button type="submit" disabled={sending} className="rounded border border-[#38bdf8]/60 px-2 text-[10px] text-[#38bdf8] disabled:opacity-50">{t("ask")}</button>
          </form>
          <select value={lang} onChange={(e) => setLang(e.target.value as LangCode)} aria-label="Idioma"
            className="rounded border border-[#1e2936] bg-[#10161f] px-1 py-1 text-[10px] text-[#c9d4e3]">
            {LANGUAGES.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}
          </select>
          <button onClick={() => { setDrawer(true); }} className="rounded border border-[#ef4444]/70 px-2 py-1 text-[10px] text-[#ef4444] hover:bg-[#29171b]">
            {t("talk_to_cio")}
          </button>
        </header>
        {children}
      </main>
      {drawer && <section className="fixed right-0 top-0 z-50 h-full w-full max-w-md border-l border-[#1e2936] bg-[#0d1219] p-4 shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#1e2936] pb-3">
          <h2 className="text-xs font-bold tracking-widest text-red-500">ORION CIO</h2>
          <button onClick={() => setDrawer(false)} className="text-xs text-[#71809a] hover:text-white">×</button>
        </div>
        <p className="mt-3 text-[10px] text-[#71809a]">{t("cio_drawer_hint")}</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {["Analiza oro", "Analiza XRP", "¿Comprarías ahora?", "Convoca la mesa", "Dame el Pre-NY"].map((item) => (
            <button key={item} onClick={() => { setQuestion(item); }} className="rounded border border-[#1e2936] px-2 py-1 text-[10px] text-[#9db2d0] hover:border-[#38bdf8]">{item}</button>
          ))}
        </div>
        <label className="mt-4 flex items-center gap-2 text-[10px] text-[#9db2d0]"><input type="checkbox" checked={autoTranslate} onChange={(e) => setAutoTranslate(e.target.checked)} />{t("auto_translate")}: {autoTranslate ? "ON" : "OFF"}</label>
        {reply && <div className="mt-4 rounded border border-[#1e2936] p-3 text-[11px] leading-relaxed whitespace-pre-wrap"><p>{reply}</p>{original && <details className="mt-2"><summary className="cursor-pointer text-[10px] text-[#71809a]">{t("view_original")}</summary><p className="mt-2 border-l border-[#1e2936] pl-2">{original}</p></details>}{translateWarning && <p className="mt-2 text-[10px] text-[#f59e0b]">{t("translation_unavailable")}</p>}</div>}
        {sending && <p className="mt-4 animate-pulse text-[10px] text-[#38bdf8]">{t("cio_thinking")}</p>}
        <button onClick={() => router.push("/command")} className="mt-4 rounded border border-[#22c55e]/60 px-3 py-1.5 text-[10px] text-[#22c55e]">{t("view_full_analysis")}</button>
      </section>}
    </div>
  );
}
