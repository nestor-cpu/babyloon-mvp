import { useState, Fragment } from "react";
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

// ── TASK 2: updated sample queries ──────────────────────────────────────────
const SAMPLE_QUERIES = [
  "What are the legal requirements for AI transparency under EU AI Act?",
  "Explain the risks of deploying unverified AI in healthcare",
  "How does provenance attribution work in language models?",
  "Що таке babyloon.ai?",
  "Які вимоги до прозорості ШІ в Євросоюзі?",
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
  // ── TASK 1: view mode — Reader is default ────────────────────────────────
  const [viewMode, setViewMode] = useState("reader");

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

      {/* Sub-header — Compare View toggle only (logo lives in the global navbar) */}
      <header className="border-b px-6 py-3 flex items-center"
              style={{ borderColor: "rgba(27,58,92,0.5)" }}>
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
                {SAMPLE_QUERIES.map((q) => (
                  <button
                    key={q}
                    onClick={() => setPrompt(q)}
                    className="w-full text-left text-xs px-2 py-1.5 rounded transition-colors"
                    style={{ background: "rgba(27,58,92,0.25)", color: "#5A7A9A" }}
                    onMouseEnter={(e) => e.currentTarget.style.color = "#E0E8F0"}
                    onMouseLeave={(e) => e.currentTarget.style.color = "#5A7A9A"}
                  >
                    {q}
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

          {/* CENTER: Response panel */}
          <div className="lg:col-span-5">
            <div className="rounded-xl p-5 min-h-96" style={{ background: "rgba(27,58,92,0.12)", border: "1px solid rgba(27,58,92,0.35)", overflow: "hidden" }}>

              {/* Panel header: title + legend + Reader/Expert toggle */}
              <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
                <h3 className="font-serif font-semibold" style={{ color: "#E0E8F0" }}>
                  Response with Provenance
                </h3>

                <div className="flex items-center gap-3">
                  {/* Trust legend */}
                  <div className="flex gap-2 text-xs" style={{ color: "#5A7A9A" }}>
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full inline-block" style={{ background: "#2E7D32" }} />
                      ≥ 0.8
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

                  {/* Reader / Expert toggle */}
                  <div className="flex items-center rounded-lg overflow-hidden border text-xs"
                       style={{ borderColor: "rgba(27,58,92,0.5)" }}>
                    <button
                      onClick={() => setViewMode("reader")}
                      className="px-3 py-1.5 transition-colors font-sans"
                      style={{
                        background: viewMode === "reader" ? "rgba(197,150,58,0.18)" : "transparent",
                        color:      viewMode === "reader" ? "#C5963A" : "#5A7A9A",
                        fontWeight: viewMode === "reader" ? "600" : "400",
                      }}
                    >
                      Reader
                    </button>
                    <button
                      onClick={() => setViewMode("expert")}
                      className="px-3 py-1.5 transition-colors font-sans border-l"
                      style={{
                        background:  viewMode === "expert" ? "rgba(197,150,58,0.18)" : "transparent",
                        color:       viewMode === "expert" ? "#C5963A" : "#5A7A9A",
                        fontWeight:  viewMode === "expert" ? "600" : "400",
                        borderColor: "rgba(27,58,92,0.5)",
                      }}
                    >
                      Expert
                    </button>
                  </div>
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
                viewMode === "reader"
                  ? <ReaderView tokens={result.tokens} outputText={result.output_text} />
                  : <TokenViewer tokens={result.tokens} />
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

// ── Helper components ────────────────────────────────────────────────────────

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
 * tokensToWords — aggregate per-token provenance into word-level units.
 *
 * ROOT CAUSE: Mistral/SentencePiece tokenizer, when decoding a single token
 * in isolation (tokenizer.decode([id])), drops the leading space that would
 * appear in a full-sequence decode. So joining token.text produces a string
 * with no spaces ("TheEuropeanUnion…"), while outputText from the backend
 * ("The European Union…") has correct whitespace.
 *
 * STRATEGY (outputText path — primary):
 *   1. Build a char-position index over the spaceless fullText.
 *   2. For each word in outputText (has real spaces), find that word's
 *      character run inside fullText via sequential indexOf.
 *   3. Map the found range to token(s) by char-range overlap.
 *
 * FALLBACK (no outputText): split fullText directly — works for Gemma/GGUF
 * adapters that do return spaces in individual token texts.
 */
function tokensToWords(tokens, outputText) {
  if (!tokens.length) return [];

  // Build char-position index over concatenated token texts (no spaces).
  let charPos = 0;
  const ranged = tokens.map((token) => {
    const start = charPos;
    charPos += token.text.length;
    return { token, start, end: charPos };
  });
  const fullText = tokens.map((t) => t.text).join("");

  function makeWord(wordText, wStart, wEnd) {
    const wordTokens = ranged
      .filter((r) => r.start < wEnd && r.end > wStart)
      .map((r) => r.token);
    if (!wordTokens.length) return null;
    return {
      text:        wordText,
      tokens:      wordTokens,
      trust_avg:   wordTokens.reduce((s, t) => s + (t.trust_avg ?? 0), 0) / wordTokens.length,
      attribution: wordTokens.flatMap((t) => t.attribution ?? []),
    };
  }

  // ── Primary path: use outputText for correct word boundaries ────────────
  if (outputText && outputText.trim().length > 0) {
    const words   = [];
    let searchFrom = 0;           // advance through fullText sequentially
    const wordRe   = /\S+/g;
    let match;

    while ((match = wordRe.exec(outputText)) !== null) {
      const wordText = match[0];
      // Find this exact string in fullText starting after the previous word.
      const pos = fullText.indexOf(wordText, searchFrom);
      if (pos === -1) continue;   // shouldn't happen; skip gracefully
      const wEnd = pos + wordText.length;
      searchFrom = wEnd;

      const w = makeWord(wordText, pos, wEnd);
      if (w) words.push(w);
    }

    if (words.length > 0) return words;
    // Fall through if outputText produced nothing (e.g. encoding mismatch)
  }

  // ── Fallback: split fullText directly (works when tokens carry spaces) ──
  const words  = [];
  const wordRe = /\S+/g;
  let match;
  while ((match = wordRe.exec(fullText)) !== null) {
    const wStart = match.index;
    const wEnd   = wStart + match[0].length;
    const w = makeWord(match[0], wStart, wEnd);
    if (w) words.push(w);
  }
  return words;
}

/** Trust → subtle background color for Reader View. */
function readerBg(trust) {
  if (trust >= 0.8) return "rgba(46, 125, 50, 0.15)";
  if (trust >= 0.5) return "rgba(249, 168, 37, 0.15)";
  return "rgba(204, 0, 0, 0.15)";
}

/** Trust → dot color (reused in popup). */
function trustDotColor(trust) {
  if (trust >= 0.8) return "#2E7D32";
  if (trust >= 0.5) return "#F9A825";
  return "#CC0000";
}

/**
 * ReaderView — renders model output as flowing readable text.
 * Each word is highlighted by its aggregated trust score.
 * Hover → popup with aggregated attribution (same style as TokenViewer).
 */
function ReaderView({ tokens = [], outputText = "" }) {
  const [hoveredIdx, setHoveredIdx]   = useState(null);
  const [popupPos,   setPopupPos]     = useState({ x: 0, y: 0 });

  if (!tokens.length) return null;

  const words = tokensToWords(tokens, outputText);

  const POPUP_W = 292;
  const POPUP_H = 300;
  const MARGIN  = 8;

  function handleMouseEnter(idx, e) {
    setHoveredIdx(idx);
    setPopupPos({ x: e.clientX, y: e.clientY });
  }

  const popupLeft = Math.min(
    popupPos.x + 12,
    window.innerWidth - POPUP_W - MARGIN,
  );
  const popupTop =
    popupPos.y + 16 + POPUP_H > window.innerHeight
      ? Math.max(MARGIN, popupPos.y - POPUP_H - 8)
      : popupPos.y + 16;

  const hoveredWord = hoveredIdx !== null ? words[hoveredIdx] : null;

  // Aggregate attribution by source_name (sum weights across constituent tokens)
  function aggregateAttribution(attribution) {
    const map = new Map();
    for (const a of attribution) {
      const key = a.source_name;
      if (!map.has(key)) {
        map.set(key, { ...a, weight: 0 });
      }
      map.get(key).weight += a.weight ?? 0;
    }
    // Normalise weights so they sum to ≤ 1
    const entries = [...map.values()];
    const total   = entries.reduce((s, e) => s + e.weight, 0);
    return total > 0
      ? entries.map((e) => ({ ...e, weight: e.weight / total })).sort((a, b) => b.weight - a.weight)
      : entries;
  }

  return (
    <div className="relative">
      {/* Flowing readable text */}
      <div
        className="leading-8 text-base"
        style={{
          color:        "#E0E8F0",
          whiteSpace:   "normal",
          wordBreak:    "break-word",
          overflowWrap: "break-word",
          maxWidth:     "100%",
        }}
      >
        {words.map((word, idx) => (
          <Fragment key={idx}>
            <span
              className="cursor-default rounded px-0.5 transition-all duration-100"
              style={{
                background: readerBg(word.trust_avg),
                boxShadow:  hoveredIdx === idx ? `0 0 0 1px ${trustDotColor(word.trust_avg)}44` : "none",
                display:    "inline",
                whiteSpace: "normal",
              }}
              onMouseEnter={(e) => handleMouseEnter(idx, e)}
              onMouseLeave={() => setHoveredIdx(null)}
            >
              {word.text}
            </span>{" "}
          </Fragment>
        ))}
      </div>

      {/* Hover popup — same visual style as TokenViewer popup */}
      {hoveredWord && hoveredWord.attribution?.length > 0 && (() => {
        const aggr = aggregateAttribution(hoveredWord.attribution);
        return (
          <div
            className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl p-4 text-sm pointer-events-none"
            style={{
              position:  "fixed",
              zIndex:    9999,
              top:       popupTop,
              left:      popupLeft,
              width:     POPUP_W,
              maxHeight: "320px",
              overflowY: "auto",
            }}
          >
            <div className="font-mono text-gray-400 text-xs mb-2 truncate">
              Word: <span className="text-white font-semibold">
                "{hoveredWord.text.length > 30
                    ? hoveredWord.text.slice(0, 30) + "…"
                    : hoveredWord.text}"
              </span>
              <span className="ml-2 text-gray-600">
                {hoveredWord.tokens.length} token{hoveredWord.tokens.length !== 1 ? "s" : ""}
              </span>
            </div>

            <div className="mb-2 flex items-center gap-2">
              <span
                className="border rounded px-1.5 py-0.5 font-mono text-xs"
                style={{
                  background:  hoveredWord.trust_avg >= 0.8 ? "rgba(46,125,50,0.6)"   : hoveredWord.trust_avg >= 0.5 ? "rgba(249,168,37,0.6)"  : "rgba(204,0,0,0.6)",
                  borderColor: hoveredWord.trust_avg >= 0.8 ? "#2E7D32"               : hoveredWord.trust_avg >= 0.5 ? "#F9A825"               : "#CC0000",
                  color:       hoveredWord.trust_avg >= 0.8 ? "#A5D6A7"               : hoveredWord.trust_avg >= 0.5 ? "#FFE082"               : "#EF9A9A",
                }}
              >
                trust {(hoveredWord.trust_avg * 100).toFixed(0)}%
              </span>
              <span className="text-xs" style={{ color: "#5A7A9A" }}>aggregated</span>
            </div>

            <div className="space-y-2">
              {aggr.slice(0, 5).map((attr, i) => (
                <div key={i} className="bg-gray-800 rounded-lg px-3 py-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-white font-semibold text-xs truncate max-w-36">
                      {attr.source_name}
                    </span>
                    <span className="text-indigo-300 font-mono text-xs">
                      {(attr.weight * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex gap-2 text-xs text-gray-400">
                    <span className="bg-gray-700 px-1.5 py-0.5 rounded text-xs">
                      {attr.license_class}
                    </span>
                    <span
                      className="border rounded px-1.5 py-0.5 font-mono text-xs"
                      style={{
                        background:  (attr.trust_score ?? 0) >= 0.8 ? "rgba(46,125,50,0.4)"  : (attr.trust_score ?? 0) >= 0.5 ? "rgba(249,168,37,0.4)"  : "rgba(204,0,0,0.4)",
                        borderColor: (attr.trust_score ?? 0) >= 0.8 ? "#2E7D32"              : (attr.trust_score ?? 0) >= 0.5 ? "#F9A825"               : "#CC0000",
                        color:       (attr.trust_score ?? 0) >= 0.8 ? "#A5D6A7"              : (attr.trust_score ?? 0) >= 0.5 ? "#FFE082"               : "#EF9A9A",
                      }}
                    >
                      trust {((attr.trust_score ?? 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              ))}
              {aggr.length > 5 && (
                <p className="text-xs text-center" style={{ color: "#1B3A5C" }}>
                  +{aggr.length - 5} more sources
                </p>
              )}
            </div>
          </div>
        );
      })()}
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
