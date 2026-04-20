import { useState } from "react";
import TokenViewer from "./TokenViewer";
import ManifestPanel from "./ManifestPanel";
import ChainViewer from "./ChainViewer";
import CompareView from "./CompareView";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

const AGENT_LEVELS = [
  { value: "",   label: "Unknown Agent (Fallback L2)", color: "#CC0000" },
  { value: "L2", label: "L2 — Public Access",          color: "#F9A825" },
  { value: "L1", label: "L1 — Verified Partner",       color: "#C5963A" },
  { value: "L0", label: "L0 — Full Access",             color: "#2E7D32" },
];

const MODEL_OPTIONS = [
  { value: "mistral-7b",   label: "Mistral 7B",        sub: "Default · 32K ctx",           thinking: false },
  { value: "gemma-4-12b",  label: "Gemma 4 12B",       sub: "Extended Context · 128K ctx",  thinking: true  },
  { value: "gemma-4-e4b",  label: "Gemma 4 E4B",       sub: "Edge / Mobile · 128K ctx",     thinking: true  },
];

const SAMPLE_PROMPTS = [
  "What is the capital of France?",
  "Explain how neural networks learn.",
  "What are the main causes of World War I?",
  "How does HTTPS encryption work?",
];

export default function DemoPage() {
  const [prompt, setPrompt] = useState("");
  const [agentToken, setAgentToken] = useState("");
  const [selectedLevel, setSelectedLevel] = useState("");
  const [selectedModel, setSelectedModel] = useState("mistral-7b");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showCompare, setShowCompare] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const headers = { "Content-Type": "application/json" };
      if (agentToken) headers["Authorization"] = `Bearer ${agentToken}`;

      const res = await fetch(`${API}/generate`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          prompt,
          max_new_tokens: 256,
          // Only send model_override for non-default models.
          // Omitting it for mistral-7b lets the backend use its pre-loaded
          // singleton and avoids a redundant make_adapter() call that would
          // try to load a second copy of the model on GPU servers.
          ...(selectedModel !== "mistral-7b" && { model_override: selectedModel }),
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleRegisterAgent(level) {
    try {
      const res = await fetch(`${API}/agent/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: `Demo-${level}`, level, ttl_days: 1 }),
      });
      const data = await res.json();
      setAgentToken(data.token);
      setSelectedLevel(level);
    } catch (err) {
      setError(`Failed to register agent: ${err.message}`);
    }
  }

  return (
    <div className="min-h-screen" style={{ background: "#0C1824", color: "#E0E8F0" }}>

      {/* Header */}
      <header className="border-b px-6 py-3 flex items-center gap-4"
              style={{ borderColor: "rgba(27,58,92,0.5)" }}>
        <img src="/logo-dark.png" alt="Babylon∞n.ai" className="h-7 w-auto" />
        <span className="text-sm tagline" style={{ color: "#5A7A9A" }}>Live Provenance Demo</span>
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => setShowCompare(!showCompare)}
            className="text-sm px-3 py-1.5 rounded-lg border transition-colors font-sans"
            style={{
              background:     showCompare ? "#C5963A" : "transparent",
              borderColor:    showCompare ? "#C5963A" : "rgba(27,58,92,0.5)",
              color:          showCompare ? "#0C1824" : "#5A7A9A",
            }}
          >
            Compare View
          </button>
        </div>
      </header>

      {showCompare ? (
        <CompareView prompt={prompt} />
      ) : (
        <div className="max-w-screen-2xl mx-auto px-4 py-6 grid lg:grid-cols-12 gap-6">

          {/* LEFT: Controls */}
          <div className="lg:col-span-3 space-y-4">

            {/* Agent selector */}
            <div className="rounded-xl p-4" style={{ background: "rgba(27,58,92,0.12)", border: "1px solid rgba(27,58,92,0.35)" }}>
              <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: "#5A7A9A" }}>
                Agent Identity (E2)
              </h3>
              <div className="space-y-2">
                {AGENT_LEVELS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() =>
                      opt.value
                        ? handleRegisterAgent(opt.value)
                        : (setAgentToken(""), setSelectedLevel(""))
                    }
                    className="w-full text-left px-3 py-2 rounded-lg text-sm border transition-all"
                    style={{
                      background:  selectedLevel === opt.value ? "rgba(197,150,58,0.1)" : "transparent",
                      borderColor: selectedLevel === opt.value ? "#C5963A" : "rgba(27,58,92,0.4)",
                    }}
                  >
                    <span className="font-mono font-semibold" style={{ color: opt.color }}>
                      {opt.value || "?"}
                    </span>
                    <span className="ml-2 text-xs" style={{ color: "#5A7A9A" }}>{opt.label}</span>
                  </button>
                ))}
              </div>
              {agentToken && (
                <div className="mt-3 p-2 rounded-lg" style={{ background: "rgba(27,58,92,0.3)" }}>
                  <p className="text-xs mb-1" style={{ color: "#5A7A9A" }}>JWT Token:</p>
                  <p className="text-xs font-mono break-all line-clamp-2" style={{ color: "#E0E8F0" }}>
                    {agentToken}
                  </p>
                </div>
              )}
            </div>

            {/* Model selector */}
            <div className="rounded-xl p-4" style={{ background: "rgba(27,58,92,0.12)", border: "1px solid rgba(27,58,92,0.35)" }}>
              <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: "#5A7A9A" }}>
                Model (БЛОК 2)
              </h3>
              <div className="space-y-2">
                {MODEL_OPTIONS.map((m) => {
                  const active = selectedModel === m.value;
                  return (
                    <button
                      key={m.value}
                      onClick={() => setSelectedModel(m.value)}
                      className="w-full text-left px-3 py-2 rounded-lg text-sm border transition-all"
                      style={{
                        background:  active ? "rgba(197,150,58,0.1)" : "transparent",
                        borderColor: active ? "#C5963A" : "rgba(27,58,92,0.4)",
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold" style={{ color: active ? "#C5963A" : "#E0E8F0" }}>
                          {m.label}
                        </span>
                        {m.thinking && (
                          <span className="text-xs px-1.5 py-0.5 rounded font-mono"
                                style={{ background: "rgba(197,150,58,0.15)", color: "#C5963A" }}>
                            think
                          </span>
                        )}
                      </div>
                      <p className="text-xs mt-0.5" style={{ color: "#5A7A9A" }}>{m.sub}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Query input */}
            <div className="rounded-xl p-4" style={{ background: "rgba(27,58,92,0.12)", border: "1px solid rgba(27,58,92,0.35)" }}>
              <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: "#5A7A9A" }}>
                Query
              </h3>

              <div className="space-y-1 mb-3">
                {SAMPLE_PROMPTS.map((p) => (
                  <button
                    key={p}
                    onClick={() => setPrompt(p)}
                    className="w-full text-left text-xs px-2 py-1.5 rounded transition-colors"
                    style={{ background: "rgba(27,58,92,0.25)", color: "#5A7A9A" }}
                    onMouseEnter={(e) => e.currentTarget.style.color = "#E0E8F0"}
                    onMouseLeave={(e) => e.currentTarget.style.color = "#5A7A9A"}
                  >
                    {p}
                  </button>
                ))}
              </div>

              <form onSubmit={handleSubmit}>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Enter your prompt..."
                  rows={4}
                  className="w-full rounded-lg px-3 py-2 text-sm resize-none focus:outline-none"
                  style={{ background: "rgba(27,58,92,0.3)", color: "#E0E8F0", border: "1px solid rgba(27,58,92,0.4)" }}
                  onFocus={(e) => e.target.style.borderColor = "#C5963A"}
                  onBlur={(e) => e.target.style.borderColor = "rgba(27,58,92,0.4)"}
                />
                <button
                  type="submit"
                  disabled={loading || !prompt.trim()}
                  className="w-full mt-2 py-2 rounded-lg font-semibold text-sm transition-all"
                  style={{
                    background:  loading || !prompt.trim() ? "rgba(27,58,92,0.3)" : "#C5963A",
                    color:       loading || !prompt.trim() ? "#5A7A9A" : "#0C1824",
                    cursor:      loading || !prompt.trim() ? "not-allowed" : "pointer",
                  }}
                >
                  {loading ? "Generating..." : "Generate"}
                </button>
              </form>

              {error && (
                <p className="mt-2 text-xs rounded-lg px-3 py-2"
                   style={{ color: "#CC0000", background: "rgba(204,0,0,0.1)", border: "1px solid rgba(204,0,0,0.2)" }}>
                  {error}
                </p>
              )}
            </div>

            {/* Session metrics */}
            {result?.summary && (
              <div className="rounded-xl p-4" style={{ background: "rgba(27,58,92,0.12)", border: "1px solid rgba(27,58,92,0.35)" }}>
                <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: "#5A7A9A" }}>
                  Session Metrics
                </h3>
                <MetricRow
                  label="License Purity"
                  value={(result.summary.license_purity * 100).toFixed(1) + "%"}
                  color={result.summary.license_purity > 0.8 ? "#2E7D32" : "#F9A825"}
                />
                <MetricRow
                  label="High Trust Tokens"
                  value={(result.summary.high_trust_ratio * 100).toFixed(1) + "%"}
                  color={result.summary.high_trust_ratio > 0.7 ? "#2E7D32" : "#F9A825"}
                />
                <MetricRow label="Total Tokens" value={result.summary.total_tokens} />
                <MetricRow
                  label="Agent Level"
                  value={result.agent_level}
                  color={
                    result.agent_level === "L0" ? "#2E7D32" :
                    result.agent_level === "L1" ? "#C5963A" : "#F9A825"
                  }
                />
                <MetricRow
                  label="Model"
                  value={result.model_backend || selectedModel}
                  color="#C5963A"
                />
                {result.thinking_mode && (
                  <MetricRow label="Thinking Mode" value="Active" color="#C5963A" />
                )}
                {result.summary.reasoning_hash && (
                  <div className="pt-1.5 text-xs" style={{ color: "#5A7A9A" }}>
                    <span>Thinking SHA-256: </span>
                    <span className="font-mono" style={{ color: "#1B3A5C", fontSize: "0.65rem" }}>
                      {result.summary.reasoning_hash.slice(0, 16)}…
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* CENTER: Token viewer */}
          <div className="lg:col-span-5">
            <div className="rounded-xl p-5 min-h-96" style={{ background: "rgba(27,58,92,0.12)", border: "1px solid rgba(27,58,92,0.35)" }}>
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-serif font-semibold" style={{ color: "#E0E8F0" }}>
                  Response with Provenance
                </h3>
                <div className="flex gap-3 text-xs" style={{ color: "#5A7A9A" }}>
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full inline-block" style={{ background: "#2E7D32" }} />
                    trust ≥ 0.8
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full inline-block" style={{ background: "#F9A825" }} />
                    0.5–0.8
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full inline-block" style={{ background: "#CC0000" }} />
                    &lt; 0.5
                  </span>
                </div>
              </div>

              {loading && (
                <div className="flex items-center gap-2 text-sm" style={{ color: "#5A7A9A" }}>
                  <div className="animate-spin w-4 h-4 rounded-full border-2"
                       style={{ borderColor: "#C5963A", borderTopColor: "transparent" }} />
                  Generating with provenance tracking...
                </div>
              )}

              {result && !loading && (
                <TokenViewer tokens={result.tokens} />
              )}

              {!result && !loading && (
                <p className="text-sm text-center pt-20" style={{ color: "#1B3A5C" }}>
                  Select an agent level and enter a prompt to see live provenance attribution.
                </p>
              )}
            </div>

            {/* Reasoning Trace — Gemma 4 only */}
            {result?.reasoning_trace && (
              <ReasoningPanel
                trace={result.reasoning_trace}
                model={result.model_backend}
              />
            )}
          </div>

          {/* RIGHT: Manifest + Chain */}
          <div className="lg:col-span-4 space-y-4">
            <ManifestPanel
              sessionId={result?.session_id}
              summary={result?.summary}
              tokens={result?.tokens}
            />
            <ChainViewer />
          </div>
        </div>
      )}
    </div>
  );
}

function MetricRow({ label, value, color = "#E0E8F0" }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b text-sm"
         style={{ borderColor: "rgba(27,58,92,0.3)" }}>
      <span style={{ color: "#5A7A9A" }}>{label}</span>
      <span className="font-mono font-semibold" style={{ color }}>{value}</span>
    </div>
  );
}

/**
 * ReasoningPanel — collapsible panel showing Gemma 4 thinking trace.
 * Only rendered when result.reasoning_trace is non-null.
 */
function ReasoningPanel({ trace, model }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl mt-3" style={{ border: "1px solid rgba(197,150,58,0.3)", background: "rgba(197,150,58,0.04)" }}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold"
        style={{ color: "#C5963A" }}
      >
        <span className="flex items-center gap-2">
          <span className="text-xs px-1.5 py-0.5 rounded font-mono"
                style={{ background: "rgba(197,150,58,0.15)", color: "#C5963A" }}>
            ✦ think
          </span>
          Reasoning Trace
          <span className="text-xs font-normal" style={{ color: "#5A7A9A" }}>
            · {model}
          </span>
        </span>
        <span style={{ fontSize: "0.7rem", color: "#5A7A9A" }}>{open ? "▲ hide" : "▼ show"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4">
          <div
            className="text-xs leading-relaxed whitespace-pre-wrap rounded-lg px-3 py-3 font-mono"
            style={{
              background: "rgba(27,58,92,0.25)",
              color: "#5A7A9A",
              maxHeight: "14rem",
              overflowY: "auto",
              borderLeft: "2px solid rgba(197,150,58,0.4)",
            }}
          >
            {trace}
          </div>
          <p className="text-xs mt-2" style={{ color: "rgba(90,122,154,0.6)" }}>
            Thinking tokens are excluded from provenance attribution (E1).
          </p>
        </div>
      )}
    </div>
  );
}
