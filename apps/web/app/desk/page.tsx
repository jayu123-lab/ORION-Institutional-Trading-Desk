"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { API_URL as API } from "@/lib/api";

type Msg = { id: number; author: string; content: string; ts: string };

type ActivityEntry = { agent: string; action: string; status: string };

type SourceRef = {
  field: string;
  source: string | null;
  ts: string | null;
  provenance: string | null;
};

type CioPayload = {
  reply?: string;
  routing?: { intent: string; asset: string | null };
  activity?: ActivityEntry[];
  sources?: SourceRef[];
  audit?: { verdict: string; gaps: string[] };
};

const QUICK_ACTIONS: { label: string; message: string }[] = [
  { label: "ANALYZE GOLD", message: "Analiza XAUUSD" },
  { label: "ANALYZE XRP", message: "Analiza XRP" },
  { label: "ANALYZE NASDAQ", message: "Analiza NASDAQ" },
  { label: "CONVENE DESK", message: "Convoca la mesa para XAUUSD" },
  { label: "MACRO BRIEF", message: "Dame un macro brief" },
  { label: "RISK CHECK", message: "@risk-manager revisa el riesgo de XAUUSD" },
];

export default function DeskRoom() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [room] = useState("desk");
  const [sending, setSending] = useState(false);
  const [lastCio, setLastCio] = useState<CioPayload | null>(null);
  const [deskState, setDeskState] = useState<string>("…");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API}/api/v1/chat/history?room=${room}&limit=200`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then(setMessages)
      .catch(() => setMessages([]));
    fetch(`${API}/api/v1/system/status`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => s && setDeskState(s.overall))
      .catch(() => setDeskState("UNKNOWN"));
  }, [room]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendContent(content: string) {
    if (!content || sending) return;
    setSending(true);
    try {
      const res = await fetch(`${API}/api/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, room }),
      });
      if (res.ok) {
        const payload = await res.json();
        if (payload.cio) setLastCio(payload.cio);
      } else {
        setMessages((m) => [
          ...m,
          { id: Date.now(), author: "system", content: `ERROR ${res.status}`, ts: "" },
        ]);
      }
      await refresh();
    } finally {
      setSending(false);
    }
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    const content = input.trim();
    setInput("");
    await sendContent(content);
  }

  async function refresh() {
    const r = await fetch(`${API}/api/v1/chat/history?room=${room}&limit=200`, { cache: "no-store" });
    if (r.ok) setMessages(await r.json());
  }

  return (
    <div className="flex flex-col gap-3 h-[calc(100vh-40px)]">
      {/* header */}
      <div className="panel px-3 py-2 flex items-center justify-between">
        <div>
          <span className="tracking-[0.2em] text-[13px] text-white">ORION CIO</span>
          <span className="text-[#71809a] text-[10px] ml-2">INSTITUTIONAL DESK · PAPER MODE</span>
        </div>
        <div className="flex items-center gap-2 text-[10px]">
          <span>DESK STATUS:</span>
          <span
            className={
              deskState === "OPERATIONAL"
                ? "text-[#22c55e]"
                : deskState === "DEGRADED"
                  ? "text-[#f59e0b]"
                  : "text-[#ef4444]"
            }
          >
            ● {deskState}
          </span>
        </div>
      </div>

      <div className="flex gap-3 flex-1 min-h-0">
        {/* chat column */}
        <div className="panel flex-1 flex flex-col min-h-0 min-w-0">
          <div className="panel-title flex justify-between">
            <span>ROOM #{room}</span>
            <button
              onClick={() => void refresh()}
              className="normal-case tracking-normal hover:text-white text-[10px]"
            >
              ⟳ reload
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {messages.length === 0 && (
              <p className="text-[#71809a]">
                Talk to the ORION CIO — it routes to the right specialists. Use @mention only to
                reach a specific agent directly.
              </p>
            )}
            {messages.map((m) => (
              <div key={m.id} className="max-w-3xl">
                <span
                  className={
                    m.author === "user"
                      ? "text-[#38bdf8]"
                      : m.author === "system"
                        ? "text-[#ef4444]"
                        : "text-[#22c55e]"
                  }
                >
                  [{m.author}]
                </span>{" "}
                <span className="text-[#71809a] text-[10px]">{m.ts.slice(11, 19)}</span>
                <p className="whitespace-pre-wrap leading-relaxed ml-2 border-l border-[#1e2936] pl-3 mt-0.5">
                  {m.content}
                </p>
              </div>
            ))}
            {sending && <p className="text-[#71809a] animate-pulse text-[11px]">CIO convening specialists…</p>}
            <div ref={bottomRef} />
          </div>

          <form onSubmit={send} className="flex gap-2 p-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask the ORION CIO — e.g. Analiza XAUUSD / ¿Comprarías oro ahora?"
              className="flex-1 bg-[#10161f] border border-[#1e2936] rounded px-3 py-2 outline-none focus:border-[#38bdf8]"
              disabled={sending}
            />
            <button
              type="submit"
              disabled={sending}
              className="bg-[#141c28] border border-[#1e2936] rounded px-5 text-[12px] tracking-wider hover:bg-[#1e2936] disabled:opacity-50"
            >
              SEND
            </button>
          </form>

          <div className="flex flex-wrap gap-2 px-2 pb-2">
            {QUICK_ACTIONS.map((a) => (
              <button
                key={a.label}
                onClick={() => void sendContent(a.message)}
                disabled={sending}
                className="text-[10px] px-2.5 py-1 rounded-full border border-[#1e2936] text-[#9db2d0] hover:text-white hover:border-[#38bdf8] disabled:opacity-50"
              >
                {a.label}
              </button>
            ))}
          </div>
        </div>

        {/* activity / sources column */}
        <div className="w-72 shrink-0 hidden lg:flex flex-col gap-3 min-h-0">
          <div className="panel p-3 overflow-y-auto min-h-0">
            <div className="panel-title mb-2 !px-0 !pt-0">LAST PIPELINE ACTIVITY</div>
            {!lastCio && (
              <p className="text-[#71809a] text-[10px]">
                Send a message to see which agents ran.
              </p>
            )}
            <ul className="space-y-1.5">
              {(lastCio?.activity ?? []).map((a, i) => (
                <li key={i} className="text-[10px] leading-snug flex gap-1.5">
                  <span
                    className={
                      a.status === "ok"
                        ? "text-[#22c55e]"
                        : a.status === "veto"
                          ? "text-[#f59e0b]"
                          : a.status === "warn"
                            ? "text-[#f59e0b]"
                            : "text-[#ef4444]"
                    }
                  >
                    {a.status === "ok" ? "✓" : a.status === "error" || a.status === "failed" ? "✗" : "⚠"}
                  </span>
                  <span>
                    <span className="text-[#cbd5e1]">{a.agent}</span>{" "}
                    <span className="text-[#71809a]">— {a.action}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div className="panel p-3 overflow-y-auto min-h-0">
            <div className="panel-title mb-2 !px-0 !pt-0">
              DATA SOURCES{" "}
              {lastCio?.audit?.verdict && (
                <span
                  className={
                    lastCio.audit.verdict.startsWith("PASS")
                      ? "text-[#22c55e]"
                      : lastCio.audit.verdict === "FAILED"
                        ? "text-[#ef4444]"
                        : "text-[#f59e0b]"
                  }
                >
                  · {lastCio.audit.verdict}
                </span>
              )}
            </div>
            {!lastCio && (
              <p className="text-[#71809a] text-[10px]">No pipeline run yet in this session.</p>
            )}
            <ul className="space-y-1">
              {(lastCio?.sources ?? []).map((s, i) => (
                <li key={i} className="text-[10px] leading-snug">
                  <span className="text-[#38bdf8]">{s.field}</span>{" "}
                  <span className="text-[#71809a]">
                    {s.source ?? "?"} · {s.provenance ?? ""}
                  </span>
                </li>
              ))}
            </ul>
            {!!lastCio?.audit?.gaps?.length && (
              <p className="text-[10px] mt-2 text-[#f59e0b]">
                GAPS: {lastCio.audit.gaps.join(", ")}
              </p>
            )}
            {lastCio?.routing && (
              <p className="text-[10px] mt-2 text-[#71809a]">
                ROUTED: {lastCio.routing.intent}
                {lastCio.routing.asset ? ` → ${lastCio.routing.asset}` : ""}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
