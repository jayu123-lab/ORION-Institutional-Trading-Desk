"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { API_URL as API } from "@/lib/api";

type Msg = { id: number; author: string; content: string; ts: string };

const AGENTS = [
  "orion-cio",
  "orion-macro",
  "orion-metals",
  "orion-crypto",
  "orion-equities",
  "orion-liquidity",
  "orion-news",
  "orion-risk-manager",
];

export default function DeskRoom() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [room] = useState("desk");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API}/api/v1/chat/history?room=${room}&limit=200`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then(setMessages)
      .catch(() => setMessages([]));
  }, [room]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(e: FormEvent) {
    e.preventDefault();
    const content = input.trim();
    if (!content || sending) return;
    setInput("");
    setSending(true);
    try {
      const res = await fetch(`${API}/api/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, room }),
      });
      if (res.ok) {
        await refresh();
      } else {
        setMessages((m) => [
          ...m,
          { id: Date.now(), author: "system", content: `ERROR ${res.status}`, ts: "" },
        ]);
      }
    } finally {
      setSending(false);
    }
  }

  async function refresh() {
    const r = await fetch(`${API}/api/v1/chat/history?room=${room}&limit=200`, { cache: "no-store" });
    if (r.ok) setMessages(await r.json());
  }

  return (
    <div className="flex flex-col gap-3 h-[calc(100vh-40px)]">
      <div className="panel flex-1 flex flex-col min-h-0">
        <div className="panel-title flex justify-between">
          <span>ORION DESK · ROOM #{room}</span>
          <button onClick={() => void refresh()} className="normal-case tracking-normal hover:text-white text-[10px]">
            ⟳ reload
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {messages.length === 0 && (
            <p className="text-[#71809a]">
              Sin mensajes. Menciona un agente con @nombre (ej: @orion-metals ¿cómo está XAUUSD?)
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
          <div ref={bottomRef} />
        </div>
      </div>

      <form onSubmit={send} className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="@orion-metals análisis XAUUSD..."
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

      <div className="flex flex-wrap gap-2 pb-1">
        {AGENTS.map((a) => (
          <button
            key={a}
            onClick={() => setInput(`@${a} `)}
            className="text-[10px] px-2 py-0.5 rounded-full border border-[#1e2936] text-[#71809a] hover:text-white hover:border-[#38bdf8]"
          >
            @{a}
          </button>
        ))}
      </div>
    </div>
  );
}
