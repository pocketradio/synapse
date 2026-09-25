"use client";

import { useCallback, useEffect, useState } from "react";

type State = "healthy" | "degraded" | "unhealthy" | "loading";

type Health = {
  status: Exclude<State, "loading">;
  application: { name: string; environment: string; api: string };
  services: {
    database: { status: State; pgvector: string; detail?: string | null };
    ollama: {
      status: State;
      chat_model: { name: string; available: boolean };
      embedding_model: { name: string; available: boolean };
      detail?: string | null;
    };
  };
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function StatusDot({ state }: { state: State }) {
  return <span className={`status-dot ${state}`} aria-label={state} />;
}

function StatusCard({
  label,
  state,
  value,
  note,
}: {
  label: string;
  state: State;
  value: string;
  note: string;
}) {
  return (
    <article className="status-card">
      <div className="status-card__top">
        <span className="eyebrow">{label}</span>
        <StatusDot state={state} />
      </div>
      <strong>{value}</strong>
      <p>{note}</p>
    </article>
  );
}

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const response = await fetch(`${API_URL}/api/health`, { cache: "no-store" });
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      setHealth(await response.json());
      setError(null);
    } catch (caught) {
      setHealth(null);
      setError(caught instanceof Error ? caught.message : "Unable to reach the API");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    let active = true;

    async function initialLoad() {
      try {
        const response = await fetch(`${API_URL}/api/health`, { cache: "no-store" });
        if (!response.ok) throw new Error(`API returned ${response.status}`);
        const result: Health = await response.json();
        if (active) {
          setHealth(result);
          setError(null);
        }
      } catch (caught) {
        if (active) {
          setHealth(null);
          setError(caught instanceof Error ? caught.message : "Unable to reach the API");
        }
      }
    }

    void initialLoad();
    return () => {
      active = false;
    };
  }, []);

  const database = health?.services.database;
  const ollama = health?.services.ollama;

  return (
    <main>
      <nav>
        <div className="brand-mark">S</div>
        <div>
          <div className="brand">Synapse</div>
          <div className="brand-subtitle">Knowledge engineering system</div>
        </div>
        <div className="step-pill">Foundation · Step 1 of 8</div>
      </nav>

      <section className="hero">
        <div>
          <div className="kicker">SYSTEM BOUNDARIES</div>
          <h1>Know what is running.<br />Trust what comes next.</h1>
          <p className="hero-copy">
            Before Synapse can reason over knowledge, every dependency must be explicit and
            independently observable. This screen is the contract for our local stack.
          </p>
        </div>
        <div className={`overall ${health?.status ?? (error ? "unhealthy" : "loading")}`}>
          <StatusDot state={health?.status ?? (error ? "unhealthy" : "loading")} />
          <div>
            <span>Overall system</span>
            <strong>{health?.status ?? (error ? "unreachable" : "checking")}</strong>
          </div>
          <button onClick={() => void refresh()} disabled={refreshing}>
            {refreshing ? "Checking…" : "Refresh"}
          </button>
        </div>
      </section>

      {error && (
        <div className="error-banner">
          FastAPI is not reachable at {API_URL}. Start the backend, then refresh. Detail: {error}
        </div>
      )}

      <section className="grid">
        <StatusCard
          label="Application API"
          state={health ? "healthy" : error ? "unhealthy" : "loading"}
          value="FastAPI"
          note={health ? `Responding in ${health.application.environment} mode` : "Awaiting API response"}
        />
        <StatusCard
          label="Durable memory"
          state={database?.status ?? "loading"}
          value="PostgreSQL"
          note={database?.detail ?? `pgvector ${database?.pgvector ?? "checking"}`}
        />
        <StatusCard
          label="Reasoning model"
          state={ollama?.chat_model.available ? "healthy" : ollama?.status ?? "loading"}
          value={ollama?.chat_model.name ?? "qwen3.5:9b"}
          note={ollama?.chat_model.available ? "Ready for structured reasoning" : "Model not available yet"}
        />
        <StatusCard
          label="Semantic model"
          state={ollama?.embedding_model.available ? "healthy" : ollama?.status ?? "loading"}
          value={ollama?.embedding_model.name ?? "qwen3-embedding:0.6b"}
          note={ollama?.embedding_model.available ? "Ready to create vectors" : "Model not available yet"}
        />
      </section>

      <section className="flow-section">
        <div>
          <span className="eyebrow">BOUNDARY MAP</span>
          <h2>One request, four clear responsibilities</h2>
        </div>
        <div className="flow">
          <div><span>01</span><strong>Browser</strong><small>presents system state</small></div>
          <b>→</b>
          <div><span>02</span><strong>FastAPI</strong><small>coordinates checks</small></div>
          <b>→</b>
          <div><span>03</span><strong>PostgreSQL</strong><small>persists knowledge</small></div>
          <b>+</b>
          <div><span>04</span><strong>Ollama</strong><small>runs local models</small></div>
        </div>
      </section>
    </main>
  );
}
