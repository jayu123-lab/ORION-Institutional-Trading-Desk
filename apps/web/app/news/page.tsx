"use client";

import { usePolling } from "@/lib/usePolling";

type NewsRow = {
  id: number;
  title: string;
  source: string;
  relevance: string | null;
  published_at: string;
  assets: string[];
};

export default function NewsPage() {
  const { data, error, loading } = usePolling<NewsRow[]>("/api/v1/news?limit=50", 30000);

  return (
    <div className="panel">
      <div className="panel-title">News Flow · últimos titulares</div>
      {error ? (
        <p className="p-4 text-[#ef4444]">API offline — {error}</p>
      ) : loading ? (
        <p className="p-4 text-[#71809a]">cargando…</p>
      ) : (data ?? []).length === 0 ? (
        <p className="p-4 text-[#71809a]">
          Sin noticias en base de datos. NO DATA AVAILABLE — la ingesta de news
          llega con los providers de Fase 2.
        </p>
      ) : (
        <ul className="divide-y divide-[#141c28]">
          {(data ?? []).map((n) => (
            <li key={n.id} className="px-3 py-2 hover:bg-[#141c28]">
              <div className="flex items-baseline justify-between gap-3">
                <span className="leading-snug">{n.title}</span>
                <span className="shrink-0 text-[10px] text-[#71809a]">
                  {n.published_at.slice(0, 16)}
                </span>
              </div>
              <div className="mt-0.5 text-[10px] text-[#71809a]">
                fuente: {n.source}
                {n.relevance ? ` · relevance ${n.relevance}` : ""}
                {(n.assets ?? []).length > 0 && ` · ${n.assets.join(", ")}`}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
