"use client";

import { ChangeEvent, DragEvent, FormEvent, useMemo, useRef, useState } from "react";

type ChatResult = {
  answer: string;
  steps: string[];
  sources: string[];
  approved: boolean;
  critic_reason: string;
  session_id: string;
};

type IngestResponse = { ingested_chunks: number; source: string };
type Source = { name: string; chunks: number };

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const STEP_META: Record<string, { label: string; dot: string }> = {
  memory: { label: "Recalling context", dot: "var(--muted-2)" },
  "supervisor->retriever": { label: "Routed to documents", dot: "var(--indigo)" },
  "supervisor->web": { label: "Routed to web search", dot: "var(--indigo)" },
  "supervisor->data": { label: "Routed to database", dot: "var(--indigo)" },
  "supervisor->code": { label: "Routed to calculation", dot: "var(--indigo)" },
  "supervisor->finish": { label: "Routed to finish", dot: "var(--indigo)" },
  retriever: { label: "Searched documents", dot: "var(--violet)" },
  web: { label: "Searched the web", dot: "var(--amber)" },
  "data(sql)": { label: "Queried the database", dot: "var(--cyan)" },
  code: { label: "Ran a calculation", dot: "var(--pink)" },
  generate: { label: "Drafted an answer", dot: "var(--ink)" },
  "critic(approved)": { label: "Verified", dot: "var(--mint)" },
  "critic(revise)": { label: "Sent back for revision", dot: "var(--coral)" },
};

function describeStep(step: string): { label: string; dot: string } {
  if (STEP_META[step]) return STEP_META[step];
  if (step.startsWith("supervisor")) return { label: step.replace("->", " → "), dot: "var(--indigo)" };
  if (step.startsWith("data")) return { label: "Queried the database", dot: "var(--cyan)" };
  if (step.startsWith("web")) return { label: "Searched the web", dot: "var(--amber)" };
  if (step.startsWith("code")) return { label: "Ran a calculation", dot: "var(--pink)" };
  if (step.startsWith("critic")) return { label: step, dot: "var(--amber)" };
  return { label: step, dot: "var(--muted-2)" };
}

export default function Home() {
  const [question, setQuestion] = useState(
    "How many customers churned in Q1 2025, and what were the main reasons?"
  );
  const [sessionId] = useState(() => crypto.randomUUID());
  const [steps, setSteps] = useState<string[]>([]);
  const [result, setResult] = useState<ChatResult | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);

  const [pasteText, setPasteText] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [ingesting, setIngesting] = useState(false);
  const [ingestError, setIngestError] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const readable = useMemo(() => steps.map(describeStep), [steps]);
  const maxLen = 4000;

  async function ask(event: FormEvent) {
    event.preventDefault();
    setRunning(true);
    setError("");
    setResult(null);
    setSteps([]);
    try {
      const response = await fetch(`${API_URL}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: sessionId }),
      });
      if (!response.ok || !response.body) throw new Error((await response.text()) || "The API request failed.");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const item of events) {
          const type = item.match(/^event: (.+)$/m)?.[1];
          const raw = item.match(/^data: (.+)$/m)?.[1];
          if (!raw) continue;
          const data = JSON.parse(raw);
          if (type === "step") setSteps(data.steps || []);
          if (type === "result") {
            setResult(data);
            setSteps(data.steps || []);
          }
          if (type === "error") throw new Error(data.detail || "The agent graph failed.");
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unexpected error");
    } finally {
      setRunning(false);
    }
  }

  async function ingestFile(file: File) {
    setIngesting(true);
    setIngestError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch(`${API_URL}/ingest/file`, { method: "POST", body: form });
      if (!response.ok) throw new Error((await response.text()) || "Could not read that file.");
      const data: IngestResponse = await response.json();
      setSources((prev) => [...prev, { name: data.source, chunks: data.ingested_chunks }]);
    } catch (caught) {
      setIngestError(caught instanceof Error ? caught.message : "Upload failed");
    } finally {
      setIngesting(false);
    }
  }

  async function ingestPastedText() {
    if (!pasteText.trim()) return;
    setIngesting(true);
    setIngestError("");
    try {
      const response = await fetch(`${API_URL}/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: pasteText, source: "pasted text" }),
      });
      if (!response.ok) throw new Error((await response.text()) || "Could not add that text.");
      const data: IngestResponse = await response.json();
      setSources((prev) => [...prev, { name: data.source, chunks: data.ingested_chunks }]);
      setPasteText("");
    } catch (caught) {
      setIngestError(caught instanceof Error ? caught.message : "Ingest failed");
    } finally {
      setIngesting(false);
    }
  }

  function onFilePicked(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) ingestFile(file);
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    const file = event.dataTransfer.files?.[0];
    if (file) ingestFile(file);
  }

  return (
    <main>
      <section className="hero">
        <p className="eyebrow">Evidence-grounded · Multi-agent</p>
        <h1>AI Analyst</h1>
        <p className="lede">
          Ground it in your own data, then ask. A supervisor routes your question to SQL, documents, the web,
          or a calculator, and a critic checks every answer before you see it.
        </p>
      </section>

      <section className="panel">
        <h2>Sources</h2>
        <p className="panel-hint">Optional — add documents so the retriever agent has something to search.</p>
        <div className="sources-grid">
          <div
            className={`dropzone${dragActive ? " active" : ""}`}
            role="button"
            tabIndex={0}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") fileInputRef.current?.click();
            }}
            onDragOver={(event) => {
              event.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={onDrop}
          >
            <strong>Drop a file</strong> or click to choose
            <br />
            .txt, .md, .csv, .pdf
            <input ref={fileInputRef} type="file" accept=".txt,.md,.csv,.pdf" onChange={onFilePicked} />
          </div>
          <div>
            <textarea
              rows={3}
              placeholder="…or paste text directly"
              value={pasteText}
              onChange={(event) => setPasteText(event.target.value)}
              aria-label="Paste text to add as a source"
            />
            <button type="button" className="ghost" onClick={ingestPastedText} disabled={ingesting || !pasteText.trim()}>
              {ingesting ? "Adding…" : "Add text"}
            </button>
          </div>
        </div>
        {ingestError && <p className="error-banner">{ingestError}</p>}
        {sources.length > 0 && (
          <ul className="source-list">
            {sources.map((source, index) => (
              <li className="source-chip" key={`${source.name}-${index}`}>
                <span className="name">{source.name}</span>
                <span className="count">{source.chunks} chunks</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <form onSubmit={ask}>
          <label htmlFor="question">Ask a business question</label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value.slice(0, maxLen))}
            rows={4}
            required
            minLength={3}
            maxLength={maxLen}
          />
          <p className="char-count">{question.length} / {maxLen}</p>
          <button className="primary" disabled={running}>
            {running ? "Analysing…" : "Run analysis"}
          </button>
        </form>
      </section>

      {error && <p className="error-banner">{error}</p>}

      <section className="grid">
        <article className="panel">
          <h2>Live agent trace</h2>
          {readable.length === 0 ? (
            <p className="empty-state">Nothing yet — run an analysis to see each agent step as it happens.</p>
          ) : (
            <ol className="ledger">
              {readable.map((step, index) => (
                <li
                  key={`${step.label}-${index}`}
                  style={{ ["--dot" as string]: step.dot }}
                  className={running && index === readable.length - 1 ? "active" : undefined}
                >
                  <span className="label">{step.label}</span>
                </li>
              ))}
            </ol>
          )}
        </article>

        <article className="panel answer">
          <h2>Verified answer</h2>
          {result ? (
            <>
              <p className="body">{result.answer}</p>
              <span className={`verdict ${result.approved ? "approved" : "revise"}`}>
                {result.approved ? "Critic approved" : "Needs another look"}
              </span>
              {!result.approved && result.critic_reason && (
                <p className="muted" style={{ marginTop: 10, fontSize: "0.88rem" }}>{result.critic_reason}</p>
              )}
              {result.sources.length > 0 && (
                <div className="sources-cited">
                  <h3>Sources</h3>
                  <ul>
                    {result.sources.map((source, index) => (
                      <li key={`${source}-${index}`}>{source}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <p className="empty-state">Your evidence-grounded answer will appear here once the graph finishes.</p>
          )}
        </article>
      </section>
    </main>
  );
}