import type { Metadata } from "next";
import "./globals.css";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "ORION Institutional Desk",
  description: "Multi-agent institutional trading desk (paper mode)",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <html lang="es"><body><AppShell>{children}</AppShell></body></html>;
}
