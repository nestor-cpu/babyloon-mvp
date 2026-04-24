import { useState } from "react";
import TokenViewer from "./TokenViewer";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

/**
 * CompareView — Split screen: Black box LLM (left) vs babyloon.ai (right)
 * Same query, dramatically different transparency.
 */
export default function CompareView({ prompt: initialPrompt = "" }) {
  const [prompt, setPrompt] = useState(initialPrompt || "What causes climate change?");
  const [leftResult, setLeftResult] = useState(null);
  const [rightResult, setRightResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleCompare() {
    if (!prompt.trim()) return;
    setLoading(true);
    setError(null);
    setLeftResult(null);
    setRightResult(null);

    try {
      // Right: babyloon.ai with provenance
      const res = await fetch(`${API}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, max_new_tokens: 200 }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Generation failed");
      }

      const data = await res.json();
      setRightResult(data);

      // Left: simulate "black box" — same text, no attribution
      setLeftResult({
        output_text: data.output_text,
        tokens: data.tokens.map((t) => ({
          ...t,
          attribution: [],
          trust_avg: null,
        })),
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-full" style={{ background: "#0C1824" }}>
      {/* Query bar */}
      <div className="border-b px-6 py-4 flex gap-4 items-start"
           style={{ borderColor: "rgba(27,58,92,0.5)" }}>
        <div className="flex-1">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={2}
            className="w-full rounded-lg px-3 py-2 text-sm resize-none focus:outline-none"
            style={{ background: "rgba(27,58,92,0.3)", color: "#E0E8F0", border: "1px solid rgba(27,58,92,0.4)" }}
            placeholder="Enter a prompt to compare..."
            onFocus={(e) => e.target.style.borderColor = "#C5963A"}
            onBlur={(e) => e.target.style.borderColor = "rgba(27,58,92,0.4)"}
          />
        </div>
        <button
          onClick={handleCompare}
          disabled={loading || !prompt.trim()}
          className="px-5 py-2 rounded-lg font-semibold text-sm transition-all whitespace-nowrap"
          style={{
            background: loading || !prompt.trim() ? "rgba(27,58,92,0.3)" : "#C5963A",
            color:      loading || !prompt.trim() ? "#5A7A9A" : "#0C1824",
            cursor:     loading || !prompt.trim() ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Generating..." : "Compare"}
        </button>
      </div>

      {error && (
        <div className="px-6 py-2 text-sm" style={{ color: "#CC0000", background: "rgba(204,0,0,0.08)" }}>
          {error}
        </div>
      )}

      {/* Split view */}
      <div className="flex flex-1 divide-x" style={{ borderColor: "rgba(27,58,92,0.4)" }}>

        {/* LEFT: Black box */}
        <div className="flex-1 p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-3 h-3 rounded-full" style={{ background: "#CC0000" }} />
            <h3 className="font-serif font-semibold" style={{ color: "#E0E8F0" }}>Standard LLM</h3>
            <span className="text-xs ml-1" style={{ color: "#5A7A9A" }}>Black Box</span>
          </div>

          {leftResult ? (
            <div className="space-y-4">
              <div className="rounded-xl p-4 leading-relaxed text-sm"
                   style={{ background: "rgba(27,58,92,0.15)", color: "#E0E8F0" }}>
                {leftResult.output_text}
              </div>

              <div className="rounded-xl p-4 space-y-2 text-sm"
                   style={{ background: "rgba(27,58,92,0.12)", border: "1px solid rgba(27,58,92,0.3)" }}>
                <BlackBoxRow label="Sources"     value="Unknown" />
                <BlackBoxRow label="License"     value="Unknown" />
                <BlackBoxRow label="Trust score" value="Unknown" />
                <BlackBoxRow label="Audit trail" value="None" />
                <BlackBoxRow label="Verifiable"  value="No" />
              </div>

              <div className="rounded-xl p-3 text-xs"
                   style={{ background: "rgba(204,0,0,0.08)", border: "1px solid rgba(204,0,0,0.25)", color: "#CC0000" }}>
                ✗ No provenance. No audit trail. No accountability.
                You cannot verify what data influenced this response.
              </div>
            </div>
          ) : (
            <div className="rounded-xl p-4 h-48 flex items-center justify-center text-sm"
                 style={{ background: "rgba(27,58,92,0.1)", color: "#1B3A5C" }}>
              {loading ? "Generating..." : "Click Compare to see the difference"}
            </div>
          )}
        </div>

        {/* RIGHT: babyloon.ai */}
        <div className="flex-1 p-6" style={{ borderLeftColor: "rgba(27,58,92,0.4)", borderLeftWidth: 1, borderLeftStyle: "solid" }}>
          <div className="flex items-center gap-2 mb-4">
            <div className="w-3 h-3 rounded-full" style={{ background: "#2E7D32" }} />
            <h3 className="font-serif font-semibold" style={{ color: "#E0E8F0" }}>
              Babylon<span style={{ color: "#C5963A" }}>∞</span>n.ai
            </h3>
            <span className="tagline text-xs ml-1" style={{ color: "#5A7A9A" }}>where every token knows its origin</span>
          </div>

          {rightResult ? (
            <div className="space-y-4">
              <div className="rounded-xl p-4"
                   style={{ background: "rgba(27,58,92,0.12)", border: "1px solid rgba(27,58,92,0.35)" }}>
                <TokenViewer tokens={rightResult.tokens} />
              </div>

              {rightResult.summary && (
                <div className="rounded-xl p-4 space-y-2 text-sm"
                     style={{ background: "rgba(27,58,92,0.12)", border: "1px solid rgba(27,58,92,0.35)" }}>
                  <ProvRow label="License purity"      value={(rightResult.summary.license_purity * 100).toFixed(1) + "%"} />
                  <ProvRow label="High trust tokens"   value={(rightResult.summary.high_trust_ratio * 100).toFixed(1) + "%"} />
                  <ProvRow label="Sources identified"  value={rightResult.summary.dominant_sources?.length ?? 0} />
                  <ProvRow label="Audit trail"         value="JSONL manifest" />
                  <ProvRow label="Verifiable"          value="SHA-256 hash-chain" />
                </div>
              )}

              <div className="rounded-xl p-3 text-xs"
                   style={{ background: "rgba(46,125,50,0.08)", border: "1px solid rgba(46,125,50,0.25)", color: "#2E7D32" }}>
                ✓ Every token traced. Cryptographic audit trail.
                Hover any word to see source, license, and trust score.
              </div>
            </div>
          ) : (
            <div className="rounded-xl p-4 h-48 flex items-center justify-center text-sm"
                 style={{ background: "rgba(27,58,92,0.1)", color: "#1B3A5C" }}>
              {loading ? "Generating with provenance..." : "Click Compare to see provenance"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function BlackBoxRow({ label, value }) {
  return (
    <div className="flex justify-between">
      <span style={{ color: "#5A7A9A" }}>{label}</span>
      <span className="font-mono" style={{ color: "#CC0000" }}>{value}</span>
    </div>
  );
}

function ProvRow({ label, value }) {
  return (
    <div className="flex justify-between">
      <span style={{ color: "#5A7A9A" }}>{label}</span>
      <span className="font-mono font-semibold" style={{ color: "#2E7D32" }}>{value}</span>
    </div>
  );
}
