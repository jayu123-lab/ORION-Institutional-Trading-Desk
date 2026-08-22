import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "ORION Institutional Desk",
  description: "Multi-agent institutional trading desk (paper mode)",
};

const NAV = [
  ["MARKET OVERVIEW", "/"],
  ["ORION DESK", "/desk"],
  ["AGENTS", "/agents"],
  ["NEWS", "/news"],
  ["MACRO", "/macro"],
  ["TRADES", "/trades"],
  ["RISK", "/risk"],
  ["SYSTEM", "/status"],
] as const;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="min-h-screen flex">
        <aside className="w-52 shrink-0 border-r border-[#1e2936] bg-[#0d1219] p-3">
          <div className="mb-6 px-2">
            <h1 className="text-[15px] font-bold tracking-widest text-red-500">
              ORION
            </h1>
            <p className="text-[10px] text-[#71809a]">INSTITUTIONAL DESK</p>
          </div>
          <nav className="flex flex-col gap-1">
            {NAV.map(([label, href]) => (
              <Link
                key={href}
                href={href}
                className="rounded px-3 py-1.5 text-[11px] tracking-wider text-[#c9d4e3]/80 hover:bg-[#141c28] hover:text-white"
              >
                {label}
              </Link>
            ))}
          </nav>
          <div className="mt-auto pt-8 text-[10px] leading-relaxed text-[#71809a] px-2">
            PAPER MODE ONLY
            <br />
            LIVE DISABLED
          </div>
        </aside>
        <main className="flex-1 overflow-x-hidden p-4">{children}</main>
      </body>
    </html>
  );
}
