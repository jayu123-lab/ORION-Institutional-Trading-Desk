export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

export async function apiPost<T>(
  path: string,
  body: unknown
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

export type QuoteRow = {
  symbol: string;
  price?: number;
  bid?: number | null;
  ask?: number | null;
  provider?: string;
  status: string;
  ts?: string;
};

export type SystemStatus = {
  database: { status: string; engine: string };
  overall: string;
  feeds: { source: string; kind: string; status: string; last_update: string | null }[];
  uptime_seconds: number;
  live_mode: boolean;
};
