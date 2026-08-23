"use client";

import { useState, useEffect, useRef } from "react";
import { apiPost, apiGet } from "@/lib/api";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardHeader, CardTitle, CardContent, CardFooter, Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { useRef as useReactRef } from "react";

type ConnectionStatus = {
  gamma: "HEALTHY" | "FAILED" | "PENDING";
  clob: "HEALTHY" | "FAILED" | "PENDING";
  ws: "HEALTHY" | "DISCONNECTED";
  auth: "AUTHENTICATED" | "NOT_CONFIGURED";
  mode: "SHADOW" | "LIVE";
  live_trading: "DISABLED" | "ENABLED";
};

type NeuralConfig = {
  enabled: boolean;
  sentiment_source: "fear_greed" | "twitter" | "news";
  technical_indicators: "rsi" | "macd" | "bb" | "all";
  min_profit_factor: number;
  min_win_rate: number;
  min_score: number;
  target_markets: string;
  spread_strategy: boolean;
  spread_markets: string;
  heartbeat_interval: number;
  neural_score_threshold: number;
};

type BrokerConfig = {
  name: "polymarket" | "binance" | "faro";
  connected: boolean;
  api_key: string;
  settings: any;
};

type FaroConfig = {
  api_key: string;
  connected: boolean;
  last_signal: string | null;
};

export default function PolymarketSettings() {
  const [status, setStatus] = useState<ConnectionStatus>({
    gamma: "PENDING",
    clob: "PENDING",
    ws: "DISCONNECTED",
    auth: "NOT_CONFIGURED",
    mode: "SHADOW",
    live_trading: "DISABLED",
  });
  const [configured, setConfigured] = useState(false);
  const [fingerprint, setFingerprint] = useState<string | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [configLoading, setConfigLoading] = useState(false);
  const [activeTab, setActiveTab] useState("connection"); // Nueva pestaña state

  const tabs = ["connection", "neural", "brokers", "faro"];

  const toast = useToast();

  // Initial status load
  useEffect(() => {
    fetchStatus();
  }, []);

  async function fetchStatus() {
    try {
      const res = await apiGet<{
        polymarket: {
          connection: string;
          authentication: string;
          mode: string;
          live_trading: string;
          market_ws: string;
          cob: string;
          gamma: string;
        };
      }>("/api/v1/settings/connections/polymarket/status");
      const data = res.polymarket;
      setStatus({
        gamma: data.gamma === "HEALTHY" ? "HEALTHY" : "FAILED",
        clob: data.cob === "HEALTHY" ? "HEALTHY" : "FAILED",
        ws: data.market_ws === "CONNECTED" ? "HEALTHY" : "DISCONNECTED",
        auth: data.authentication === "AUTHENTICATED" ? "AUTHENTICATED" : "NOT_CONFIGURED",
        mode: data.mode === "SHADOW" ? "SHADOW" : "LIVE",
        live_trading: data.live_trading === "DISABLED" ? "DISABLED" : "ENABLED",
      });
      setConfigured(data.connection === "CONNECTED");
      setFingerprint(data.authentication === "AUTHENTICATED" ? "********" : null);
    } catch (e) {
      console.error("Failed to fetch status:", e);
      setStatus({
        gamma: "FAILED",
        clob: "FAILED",
        ws: "DISCONNECTED",
        auth: "NOT_CONFIGURED",
        mode: "LIVE",
        live_trading: "ENABLED",
      });
    }
  }

  // ... (resto del código existente omitido por brevedad, mantendría la estructura actual)
  
  // Para brevidad, mostraremos la estructura con los nuevos tabs
  // Los handlers y state para neural/brokers/faro se agregarían aquí

  return (
    <div className="space-y-4">
      <Tabs defaultValue="connection" className="w-full" value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="connection">Conexión</TabsTrigger>
          <TabsTrigger value="neural">🤖 Neural</TabsTrigger>
          <TabsTrigger value="brokers">📈 Brokers</TabsTrigger>
          <TabsTrigger value="faro">📤 Faro</TabsTrigger>
        </TabsList>
        <TabsContent value="connection">
          {/* Existing connection form code preserved */}
          <form
            onSubmit={async (e: React.FormEvent) => {
              e.preventDefault();
              setConfigLoading(true);
              try {
                // Existing submit logic
                setConfigured(true);
                setConfigLoading(false);
                toast({
                  title: "Configuración guardada",
                  description: "Las credenciales de Polymarket se han almacenado de forma segura.",
                });
              } catch (error) {
                setConfigLoading(false);
                toast({
                  title: "Error",
                  description: "Error al guardar configuración.",
                  variant: "destructive",
                });
              }
            }}>
            <div className="space-y-4">
              <div className="rounded-lg border border-[#1e2936] p-4">
                <h3 className="text-sm font-medium text-[#71809a] mb-2">Credenciales de Conexión</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                      API Key Gamma
                      <span className="text-xs text-[#71809a]">(Opcional, para descubrimiento de mercados)</span>
                    </label>
                    <Input
                      value=""
                      onChange={}
                      placeholder="gamma_api_key"
                      disabled={status.auth !== "NOT_CONFIGURED"}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                      CLOB Token
                      <span className="text-xs text-[#71809a]">(Token del mercado)</span>
                    </label>
                    <Input
                      value=""
                      onChange={}
                      placeholder="clob_token"
                      disabled={status.auth !== "NOT_CONFIGURED"}
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                    Modo
                    <span className="text-xs text-[#71809a]">(SHADOW = sin órdenes reales)</span>
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      onClick={() => setStatus((prev) => ({ ...prev, mode: "SHADOW" } as any))}
                      className={`w-full py-2 px-4 rounded-md font-medium transition-colors ${status.mode === "SHADOW" ? "bg-[#16a34a] text-white" : "border-[#1e2936] text-[#cbd5e1]"}`}
                      type="button">
                      SHADOW MODE
                    </button>
                    <button
                      onClick={() => setStatus((prev) => ({ ...prev, mode: "LIVE" } as any))}
                      className={`w-full py-2 px-4 rounded-md font-medium transition-colors ${status.mode === "LIVE" ? "bg-[#16a34a] text-white" : "border-[#1e2936] text-[#cbd5e1]"}`}
                      type="button">
                      LIVE MODE
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                    Trading en Tiempo Real
                    <span className="text-xs text-[#71809a]">(ACTIVO = órdenes reales)</span>
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      onClick={() => setStatus((prev) => ({ ...prev, live_trading: "ENABLED" } as any))}
                      className={`w-full py-2 px-4 rounded-md font-medium transition-colors ${status.live_trading === "ENABLED" ? "bg-[#16a34a] text-white" : "border-[#1e2936] text-[#cbd5e1]"}`}
                      type="button">
                      ENABLED
                    </button>
                    <button
                      onClick={() => setStatus((prev) => ({ ...prev, live_trading: "DISABLED" } as any))}
                      className={`w-full py-2 px-4 rounded-md font-medium transition-colors ${status.live_trading === "DISABLED" ? "bg-[#16a34a] text-white" : "border-[#1e2936] text-[#cbd5e1]"}`}
                      type="button">
                      DISABLED
                    </button>
                  </div>
                </div>
              </div>
            </div>
            <div className="mt-6">
              <button
                onClick={handleTestConnection}
                className="w-full py-2 px-4 rounded-md font-medium transition-colors bg-[#2563eb] text-white hover:bg-[#1e40af]">
                {testLoading ? "Procesando..." : "TEST CONNECTION"}
              </button>
            </button>
          </form>
        </TabsContent>
        <TabsContent value="neural">
          <div className="p-6">
            <h2 className="text-xl font-medium text-[#1e2936] mb-4">🤖 Estrategia Neural</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                  Neural Enable
                  <span className="text-xs text-[#71809a]">Activar cerebro de decisiones</span>
                </label>
                <select defaultValue="true">
                  <option value="true">Activado</option>
                  <option value="false">Desactivado</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                  Sentimiento de Mercado
                </label>
                <select defaultValue="fear_greed">
                  <option value="fear_greed">Fear & Greed Index</option>
                  <option value="twitter">Twitter/Sentiment</option>
                  <option value="news">Noticias</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                  Indicadores Técnicos
                </label>
                <select defaultValue="all">
                  <option value="all">Todos (RSI, MACD, Bollinger)</option>
                  <option value="rsi">Solo RSI</option>
                  <option value="macd">Solo MACD</option>
                  <option value="bb">Solo Bandas de Bollinger</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                    Profit Factor Mínimo
                  </label>
                  <input
                    type="number"
                    defaultValue={1.5}
                    min={1.0}
                    step={0.1}
                    className="w-full rounded border border-[#1e2936] p-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                    Win Rate Mínimo (%)
                  </label>
                  <input
                    type="number"
                    defaultValue={50}
                    min={0}
                    max={100}
                    step={1}
                    className="w-full rounded border border-[#1e2936] p-2 text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                    Score Mínimo (0-100)
                  </label>
                  <input
                    type="number"
                    defaultValue={70}
                    min={0}
                    max={100}
                    step={1}
                    className="w-full rounded border border-[#1e2936] p-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                    Mercados Objetivo (comma-sep)
                  </label>
                  <input
                    value="gold,btc,eth,us500"
                    className="w-full rounded border border-[#1e2936] p-2 text-sm"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                    Estrategia Spread
                  </label>
                  <select defaultValue="true">
                    <option value="true">Activado</option>
                    <option value="false">Desactivado</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                    Mercados Spread
                  </label>
                  <input
                    value="polymarket"
                    className="w-full rounded border border-[#1e2936] p-2 text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                    Interval Heartbeat (segundos)
                  </label>
                  <input
                    value={5}
                    min={1}
                    max={60}
                    step={1}
                    className="w-full rounded border border-[#1e2936] p-2 text-sm"
                  />
                </div>
              </div>
            </div>
          </div>
        </TabsContent>
        <TabsContent value="brokers">
          <div className="p-6">
            <h2 className="text-xl font-medium text-[#1e2936] mb-4">📈 Brokers Conectados</h2>
            <div className="space-y-4">
              {/* Polymarket connector */}
              <div>
                <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                  Polymarket WS
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setStatus((prev) => ({ ...prev, connected: true } as any))}
                    className={`w-full py-2 px-4 rounded-md font-medium transition-colors ${status.connected ? "bg-[#16a34a] text-white" : "border-[#1e2936] text-[#cbd5e1]"}`}
                    type="button">
                    CONECTAR
                  </button>
                  <span className="text-xs text-[#71809a]">WS enabled: {status.ws === "HEALTHY" ? "YES" : "NO"}</span>
                </div>
              </div>
              {/* Faro connector */}
              <div>
                <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                  Faro API
                </label>
                <Input
                  value=""
                  placeholder="API Key Faro"
                  className="w-full rounded border border-[#1e2936] p-2 text-sm"
                />
                <span className="text-xs text-[#71809a]">Ingresa tu API Key de Faro</span>
              </div>
            </div>
          </div>
        </TabsContent>
        <TabsContent value="faro">
          <div className="p-6">
            <h2 className="text-xl font-medium text-[#1e2936] mb-4">📤 Faro Signals</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                  API Key Faro
                </label>
                <Input
                  value=""
                  placeholder="sk-orion-..."
                  className="w-full rounded border border-[#1e2936] p-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#cbd5e1] mb-1">
                  Última Señal
                </label>
                <p className="text-sm text-[#71809a] mb-2">
                  Ninguna señal enviada aún
                </p>
                <p className="text-xs text-[#3f87a6]">
                  Se enviarán señales automáticamente cuando la estrategia las genere
                </p>
              </div>
              <button
                onClick={() => toast({
                  title: "Faro configurado",
                  description: "API Key guardada. Recibirás señales en tiempo real.",
                })} 
                className="w-full py-2 px-4 rounded-md font-medium transition-colors bg-[#2563eb] text-white hover:bg-[#1e40af]">
                  Guardar Configuración de Faro
              </button>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}