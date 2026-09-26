import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Status = "healthy" | "degraded" | "unhealthy" | "loading";
type Health = { status: Status; services: { database: { status: Status; pgvector: string }; ollama: { chat_model: { name: string }; embedding_model: { name: string } } } };
type Candidate = { candidate_id: string; kind: string; content: string; source_name: string; locator: Record<string, unknown>; score: number };
type Retrieval = { strategy: string; engine_counts: Record<string, number>; candidates: Candidate[] };
type QueryResult = { query_run_id: string; answer: string; plan: { tools: string[]; kind?: string }; events: { node: string; [key: string]: unknown }[]; candidates: Candidate[]; verification: { claim_text: string; status: string; evidence_ids: string[] }[]; route?: string; cache_level?: string; model_calls?: number; latency_ms?: number };

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const tabs = ["sources", "knowledge", "ask", "evaluation"] as const;
type Tab = (typeof tabs)[number];

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, options);
  if (!response.ok) throw new Error(`api returned ${response.status}`);
  return response.json() as Promise<T>;
}

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("ask");
  async function loadHealth() {
    try { setHealth(await api<Health>("/api/health")); setError(null); }
    catch (caught) { setHealth(null); setError(caught instanceof Error ? caught.message : "api unavailable"); }
  }
  useEffect(() => { void loadHealth(); }, []);
  const status = health?.status ?? (error ? "unhealthy" : "loading");
  return <main>
    <header><h1>synapse</h1><span className={`status ${status}`}>{status}</span></header>
    <nav aria-label="main navigation">{tabs.map((name) => <button className={tab === name ? "active" : ""} onClick={() => setTab(name)} key={name}>{name}</button>)}</nav>
    {error && <p className="error">{error}. start the backend on port 8000.</p>}
    {tab === "sources" && <Sources />}{tab === "knowledge" && <Knowledge />}{tab === "ask" && <Ask />}{tab === "evaluation" && <Evaluation />}
    <footer><button className="plain" onClick={() => void loadHealth()}>refresh health</button></footer>
  </main>;
}

function Sources() {
  const [files, setFiles] = useState<FileList | null>(null); const [result, setResult] = useState<Record<string, unknown> | null>(null); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function upload() {
    if (!files?.length) return; const form = new FormData(); Array.from(files).forEach((file) => form.append("files", file)); setBusy(true); setError(null);
    try { setResult(await api<Record<string, unknown>>("/api/sources/files", { method: "POST", body: form })); } catch (caught) { setError(caught instanceof Error ? caught.message : "upload failed"); } finally { setBusy(false); }
  }
  return <Panel label="sources" title="ingest knowledge"><p className="muted">Upload markdown, code, json, html, or pdf files.</p><input type="file" multiple onChange={(event) => setFiles(event.target.files)} /><button onClick={() => void upload()} disabled={busy || !files?.length}>{busy ? "uploading" : "upload"}</button>{error && <p className="error">{error}</p>}{result && <pre>{JSON.stringify(result, null, 2)}</pre>}</Panel>;
}

function Knowledge() {
  const [summary, setSummary] = useState<Record<string, number> | null>(null); const [question, setQuestion] = useState(""); const [result, setResult] = useState<Retrieval | null>(null); const [error, setError] = useState<string | null>(null);
  async function loadSummary() { try { setSummary(await api<Record<string, number>>("/api/knowledge/summary")); setError(null); } catch (caught) { setError(caught instanceof Error ? caught.message : "knowledge unavailable"); } }
  async function search() { if (!question.trim()) return; try { setResult(await searchRetrieval(question, "hybrid_graph")); } catch (caught) { setError(caught instanceof Error ? caught.message : "search failed"); } }
  useEffect(() => { void loadSummary(); }, []);
  return <Panel label="knowledge" title="inspect knowledge"><div className="stats">{summary ? Object.entries(summary).map(([name, value]) => <Row key={name} name={name} status={String(value)} />) : <p className="muted">loading summary</p>}</div><div className="form-row"><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="search the knowledge base" onKeyDown={(event) => event.key === "Enter" && void search()} /><button onClick={() => void search()}>search</button></div>{error && <p className="error">{error}</p>}{result && <CandidateList result={result} />}</Panel>;
}

function Ask() {
  const [question, setQuestion] = useState(""); const [result, setResult] = useState<QueryResult | null>(null); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false); const [duration, setDuration] = useState<number | null>(null);
  async function ask() { if (!question.trim()) return; setBusy(true); setError(null); const started = performance.now(); try { setResult(await api<QueryResult>("/api/query", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) })); setDuration(Math.round(performance.now() - started)); } catch (caught) { setError(caught instanceof Error ? caught.message : "query failed"); } finally { setBusy(false); } }
  return <Panel label="ask" title="ask synapse"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="ask a question about the corpus" rows={4} /><button onClick={() => void ask()} disabled={busy || !question.trim()}>{busy ? "running" : "ask"}</button>{error && <p className="error">{error}</p>}{result && <div className="answer"><h3>answer</h3><p className="answer-text">{result.answer}</p><h3>verification</h3>{result.verification.map((item, index) => <div className="claim" key={index}><span>{item.status}</span><p>{item.claim_text}</p><small>evidence: {item.evidence_ids.join(", ") || "none"}</small></div>)}<h3>execution</h3><p className="muted">route: {result.route ?? result.plan.kind ?? "?"} · tools: {result.plan.tools.join(", ")} · cache: {result.cache_level ?? "none"}</p><p className="muted">candidates: {result.candidates.length} · verified: {result.verification.length} · model calls: {result.model_calls ?? "?"} · latency: {result.latency_ms ?? duration ?? "?"}ms</p><p className="muted">nodes: {result.events.map((event) => event.node).join(" → ")}</p></div>}</Panel>;
}

function Evaluation() {
  const [question, setQuestion] = useState(""); const [results, setResults] = useState<Retrieval[]>([]); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false); const strategies = ["lexical", "vector", "hybrid", "hybrid_graph"];
  async function compare() { if (!question.trim()) return; setBusy(true); setError(null); try { setResults(await Promise.all(strategies.map((strategy) => searchRetrieval(question, strategy)))); } catch (caught) { setError(caught instanceof Error ? caught.message : "evaluation failed"); } finally { setBusy(false); } }
  return <Panel label="evaluation" title="compare retrieval"><p className="muted">Run one question through each retrieval strategy.</p><div className="form-row"><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="question to compare" /><button onClick={() => void compare()} disabled={busy || !question.trim()}>{busy ? "running" : "compare"}</button></div>{error && <p className="error">{error}</p>}{results.length > 0 && <div className="comparison">{results.map((item) => <div className="comparison-row" key={item.strategy}><span>{item.strategy}</span><span>{item.candidates.length} candidates</span><span>lexical {item.engine_counts.lexical ?? 0} · vector {item.engine_counts.vector ?? 0} · graph {item.engine_counts.graph ?? 0}</span></div>)}</div>}</Panel>;
}

async function searchRetrieval(question: string, strategy: string) {
  return api<Retrieval>("/api/retrieval/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, strategy }) });
}
function Panel({ label, title, children }: { label: string; title: string; children: React.ReactNode }) { return <section><p className="label">{label}</p><h2>{title}</h2>{children}</section>; }
function CandidateList({ result }: { result: Retrieval }) { return <div className="candidates"><p className="muted">{result.candidates.length} candidates · {result.strategy}</p>{result.candidates.map((candidate) => <article key={candidate.candidate_id}><div className="source">{candidate.source_name} · {formatLocator(candidate.locator)}</div><p>{candidate.content}</p></article>)}</div>; }
function formatLocator(locator: Record<string, unknown>) { return Object.entries(locator).map(([key, value]) => `${key}: ${value}`).join(" · "); }
function Row({ name, status }: { name: string; status: string }) { return <div className="row"><span>{name}</span><span>{status}</span></div>; }

createRoot(document.getElementById("root")!).render(<App />);
