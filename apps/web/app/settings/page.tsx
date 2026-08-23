"use client";

import { useState, useEffect, useRef } from "react";
import { apiPost, apiGet } from "@/lib/api";
import { useToast } from "@/components/ui/use-toast";

type ConnectionStatus = {
  gamma: "HEALTHY" | "FAILED" | "PENDING";
  clob: "HEALTHY" | "FAILED" | "PENDING";
  ws: "HEALTHY" | "DISCONNECTED";
  auth: "AUTHENTICATED" | "NOT_CONFIGURED";
  mode: "SHADOW" | "LIVE";
  live_trading: "DISABLED" | "ENABLED";
};

type ConfigureForm = {
  secret_type: "gamma_api_key" | "clob_token";
  api_key?: string;
  clob_token?: string;
  shadow_mode?: boolean;
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
      setFingerprint(data.authentication === "AUTHENTICATED" ? "****••••" : null);
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

  async function handleTestConnection() {
    setTestLoading(true);
    try {
      const res = await apiPost<
        {
          polymarket: {
            status: {
              gamma: string;
              midpoint: string;
              ws: string;
              auth: string;
              mode: string;
              live: string;
            };
          };
        }
      >("/api/v1/settings/connections/polymarket/test");

      const {
        polymarket: {
          status: { gamma, midpoint, ws, auth, mode, live },
        } = {},
      } = res;

      toast({
        title: "Test Connection Results",
        description: `
          GAMMA: ${gamma}
          CLOB Midpoint: ${midpoint}
          WebSocket: ${ws}
          Authentication: ${auth}
          Mode: ${mode}
          Live Trading: ${live}
        `,
      });

      // Update status after test
      fetchStatus();
    } catch (e: any) {
      toast({
        title: "Test Connection Failed",
        description: e.message || "Unknown error during test",
        variant: "destructive",
      });
    } finally {
      setTestLoading(false);
    }
  }

  async function handleConfigure(event: React.FormEvent) {
    event.preventDefault();
    setConfigLoading(true);
    try {
      // Get the form data - in a real app, use FormData
      const formData = new FormData(event.target as HTMLFormElement);
      const payload: ConfigureForm = {
        secret_type: formData.get("secret_type") as string,
        api_key: formData.get("api_key") as string,
        clob_token: formData.get("clob_token") as string,
        shadow_mode: formData.get("shadow_mode") === "true",
      };

      const res = await apiPost<
        {
          status: string;
          fingerprint: string;
          message: string;
        }
      >("/api/v1/settings/connections/polymarket/configure", payload);

      setConfigured(true);
      setFingerprint(res.fingerprint || "••••••••");
      setStatus((prev) => ({
        ...prev,
        gamma: "HEALTHY",
        auth: "AUTHENTICATED",
        mode: "SHADOW",
        live_trading: "DISABLED",
      }));

      toast({
        title: "Credentials Configured",
        description: res.message || "Polymarket credentials stored securely",
      });
    } catch (e: any) {
      toast({
        title: "Configuration Failed",
        description: e.message || "Failed to store credentials",
        variant: "destructive",
      });
    } finally {
      setConfigLoading(false);
    }
  }

  return (
    <div className="space-y-6 p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">
        POLYMARKET CONNECTIONS
      </h1>

      {/* Status Overview */}
      <div className="rounded-lg border border-[#1e2936] p-4 mb-6">
        <h2 className="text-lg font-medium mb-4">Connection Status</h2>
        <div className="grid grid-cols-2 gap-2">
          <StatusBadge
            name="Gamma"
            status={status.gamma}
            onRefresh={() => fetchStatus()}
          />
          <StatusBadge
            name="CLOB"
            status={status.clob}
            onRefresh={() => fetchStatus()}
          />
          <StatusBadge
            name="WebSocket"
            status={status.ws}
            onRefresh={() => fetchStatus()}
          />
          <StatusBadge
            name="Authentication"
            status={status.auth}
            onRefresh={() => fetchStatus()}
          />
        </div>
        <div className="mt-4 pt-4 border-t border-[#1e2936]">
          <div className="flex justify-between items-center">
            <span className="text-sm text-[#71809a]">
              Mode: {" "}
              {status.mode === "SHADOW" ? (
                <span className="text-green-400">SHADOW MODE</span>
              ) : (
                <span className="text-red-400">LIVE MODE</span>
              )}
            </span>
            <span className="text-sm text-[#71809a]">
              Live Trading: {" "}
              {status.live_trading === "DISABLED" ? (
                <span className="text-green-400">DISABLED</span>
              ) : (
                <span className="text-red-400">ENABLED</span>
              )}
            </span>
          </div>
        </div>
      </div>

      {/* TEST CONNECTION Button */}
      <div className="rounded-lg border border-[#1e2936] p-4 mb-6" testLoading={testLoading}>
        <h2 className="text-lg font-medium mb-4">Test Connection</h2>
        <button
          onClick={handleTestConnection}
          disabled={testLoading}
          className={
            "w-full py-2 px-4 rounded-md font-medium transition-colors " +
            (testLoading ? "bg-orange-500 text-white cursor-not-allowed" : "bg-[#2563eb] text-white hover:bg-[#1e40af]")
          }
        >
          {testLoading ? "TESTING..." : "TEST CONNECTION"}
        </button>
      </div>

      {/* Configure Credentials Form */}
      {configured ? (
        <ConfiguredState
          fingerprint={fingerprint}
          onReconfigure={handleConfigure}
          onRemoveCredentials={handleRemoveCredentials}
        />
      ) : (
        <ConfigureState
          onConfigure={handleConfigure}
          onTestConnection={handleTestConnection}
        />
      )}
    </div>
  );
}

function StatusBadge({
  name,
  status,
  onRefresh,
}: {
  name: string;
  status: "HEALTHY" | "FAILED" | "PENDING";
  onRefresh: () => void;
}) {
  const [localStatus, setLocalStatus] = useState(status);

  useEffect(() => {
    setLocalStatus(status);
  }, [status]);

  const statusColor = {
    HEALTHY: "text-green-400",
    FAILED: "text-red-400",
    PENDING: "text-yellow-400",
  }[localStatus];

  const statusText = {
    HEALTHY: "HEALTHY",
    FAILED: "FAILED",
    PENDING: "PENDING",
  }[localStatus];

  return (
    <div className="flex items-center gap-2">
      <span className={`${statusColor} font-medium}`>{statusText}</span>
      <span className="text-xs text-[#71809a]">{name}</span>
      <button
        onClick={onRefresh}
        className="text-[10px] text-[#71809a] hover:underline">
        ↻
      </button>
    </div>
  );
}

interface ConfigureStateProps {
  onConfigure: (event: React.FormEvent) => void;
  onTestConnection: () => void;
}

function ConfigureState({ onConfigure, onTestConnection }: ConfigureStateProps) {
  return (
    <div className="space-y-4">
      <form onSubmit={onConfigure} className="rounded-lg border border-[#1e2936] p-4">
        <h2 className="text-lg font-medium mb-4">Configure Polymarket Credentials</h2>

        <div className="mb-4">
          <label className="block text-sm font-medium mb-2">
            Authentication Method
          </label>
          <select
            name="secret_type"
            className="w-full px-3 py-2 rounded-md border border-[#3f3f4f] bg-[#1e2936] focus:outline-none focus:ring-2 focus:ring-orange-500/30"
            onChange={(e) => {
              setSecretType(e.target.value);
            }}
          >
            <option value="gamma_api_key">Gamma API Key</option>
            <option value="clob_token">CLOB Token</option>
          </select>
        </div>

        {secretType === "gamma_api_key" && (
          <div className="mb-4">
            <label className="block text-sm font-medium mb-2">
              Gamma API Key
            </label>
            <input
              type="password"
              name="api_key"
              className="w-full px-3 py-2 rounded-md border border-[#3f3f4f] bg-[#1e2936] focus:outline-none focus:ring-2 focus:ring-orange-500/30"
              placeholder="ORION_GAMMA_API_KEY..."
              required
            />
            <p className="text-xs text-[#71809a] mt-1">
              Store securely via Windows Credential Manager or .env fallback
            </p>
          </div>
        )}

        {secretType === "clob_token" && (
          <div className="mb-4">
            <label className="block text-sm font-medium mb-2">
              CLOB Token
            </label>
            <input
              type="password"
              name="clob_token"
              className="w-full px-3 py-2 rounded-md border border-[#3f3f4f] bg-[#1e2936] focus:outline-none focus:ring-2 focus:ring-orange-500/30"
              placeholder="CLOB authentication token"
              required
            />
            <p className="text-xs text-[#71809a] mt-1">
              Public CLOB access does not require token; leave blank for read-only
            </p>
          </div>
        )}

        <div className="mb-4 form-check form-check-info">
          <input
            type="checkbox"
            name="shadow_mode"
            className="form-check-input rounded-sm bg-[#1e2936] border-[#3f3f4f] cursor-pointer"
            id="shadowMode"
            defaultChecked
          />
          <label
            htmlFor="shadowMode"
            className="form-check-label text-sm text-[#71809a] cursor-pointer"
          >
            SHADOW MODE (recommended — no real orders)
          </label>
          <p className="text-xs text-[#71809a] mt-1">
            {true ? (
              "All trades are simulated (SHADOW MODE). No real orders will be sent to Polymarket."
            ) : null}
          </p>
        </div>

        <button
          type="submit"
          className="w-full py-2 px-4 rounded-md font-medium transition-colors bg-[#2563eb] text-white hover:bg-[#1e40af]">
          {secretType === "gamma_api_key" ? "CONFIGURE GAMMA" : "CONFIGURE CLOB"}
        </button>
      </form>

      <div>
        <button
          onClick={onTestConnection}
          className="w-full py-2 px-4 rounded-md font-medium transition-colors bg-[#2563eb] text-white hover:bg-[#1e40af]">
          TEST CONNECTION
        </button>
      </div>
    </div>
  );
}

interface ConfiguredStateProps {
  fingerprint: string | null;
  onReconfigure: (event: React.FormEvent) => void;
  onRemoveCredentials: () => void;
}

function ConfiguredState({
  fingerprint,
  onReconfigure,
  onRemoveCredentials,
}: ConfiguredStateProps) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-[#1e2936] p-4">
        <h2 className="text-lg font-medium mb-4">Credentials Configured</h2>
        <p className="text-sm text-[#71809a]">
          Polymarket credentials are stored securely. {" "}
          <span className="font-medium">{fingerprint || "••••••••"}</span>
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={onReconfigure}
          className="w-full py-2 px-4 rounded-md font-medium transition-colors bg-[#2563eb] text-white hover:bg-[#1e40af]">
          RECONFIGURE
        </button>
        <button
          onClick={onRemoveCredentials}
          className="w-full py-2 px-4 rounded-md font-medium transition-colors bg-[#ef4444] text-white hover:bg-[#dc2626]">
          REMOVE CREDENTIALS
        </button>
      </div>

      <p className="text-xs text-[#71809a]">
        <strong>Mode:</strong> SHADOW MODE — No real orders will be sent.
      </p>
      <p className="text-xs text-[#71809a]">
        <strong>Live Trading:</strong> DISABLED
      </p>
    </div>
  );
}

const [secretType, setSecretType] = useState("gamma_api_key");