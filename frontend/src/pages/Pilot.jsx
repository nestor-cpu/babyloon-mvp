import { useState } from "react";
import TokenViewer from "../components/TokenViewer";
import ManifestPanel from "../components/ManifestPanel";
import ChainViewer from "../components/ChainViewer";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

const SAMPLE_PROMPTS_UK = [
  "Що таке штучний інтелект?",
  "Розкажи про українську культуру.",
  "Як працює машинне навчання?",
  "Яке значення мови для нації?",
];

export default function Pilot() {
  const [prompt, setPrompt] = useState("");
  const [agentToken, setAgentToken] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`${API}/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(agentToken ? { Authorization: `Bearer ${agentToken}` } : {}),
        },
        body: JSON.stringify({ prompt, max_new_tokens: 256 }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Generation failed");
      }

      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  // Compute avg trust from tokens
  const avgTrust = (() => {
    const toks = result?.tokens ?? [];
    if (!toks.length) return 0;
    return toks.reduce((s, t) => s + (t.trust_avg ?? 0), 0) / toks.length;
  })();

  return (
    <div className="min-h-screen" style={{ background: "#0C1824", color: "#E0E8F0" }}>

      {/* Header */}
      <header className="border-b px-6 py-4 flex items-center gap-4"
              style={{ borderColor: "rgba(27,58,92,0.5)" }}>
        <div className="flex items-center gap-3">
          <img src="/icon.png" alt="babyloon.ai icon" className="h-8 w-8" />
          <div>
            <div className="font-serif text-lg font-semibold" style={{ color: "#E0E8F0" }}>
              Pilot Program
            </div>
            <div className="tagline text-xs" style={{ color: "#5A7A9A" }}>
              babyloon.ai × Сяйво — Мінцифра України
            </div>
          </div>
        </div>
        <div className="ml-auto text-xs font-mono hidden sm:block" style={{ color: "#1B3A5C" }}>
          Демонстрація для Мінцифри України
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-8">

        {/* Intro */}
        <div className="rounded-xl p-6 mb-8" style={{ background: "rgba(27,58,92,0.15)", border: "1px solid rgba(197,150,58,0.25)" }}>
          <h2 className="text-lg font-serif mb-2" style={{ color: "#C5963A" }}>
            Провенанс для національної LLM «Сяйво»
          </h2>
          <p className="text-sm leading-relaxed" style={{ color: "#E0E8F0", opacity: 0.8 }}>
            Ця сторінка демонструє, як babyloon.ai додає прозорість до україномовних LLM.
            Кожне слово у відповіді прив'язане до конкретного джерела — українські датасети,
            вікіпедія, академічні тексти. Атрибуція в реальному часі.
          </p>
        </div>

        <div className="grid lg:grid-cols-3 gap-6">

          {/* Left: Input */}
          <div className="lg:col-span-1 space-y-4">
            <div className="rounded-xl p-5" style={{ background: "rgba(27,58,92,0.12)", border: "1px solid rgba(27,58,92,0.35)" }}>
              <h3 className="font-serif font-semibold mb-4" style={{ color: "#C5963A" }}>Запит</h3>

              <div className="mb-4 space-y-2">
                <p className="text-xs mb-2" style={{ color: "#5A7A9A" }}>Приклади запитів:</p>
                {SAMPLE_PROMPTS_UK.map((p) => (
                  <button
                    key={p}
                    onClick={() => setPrompt(p)}
                    className="w-full text-left text-xs rounded-lg px-3 py-2 transition-colors"
                    style={{ background: "rgba(27,58,92,0.3)", color: "#E0E8F0" }}
                    onMouseEnter={(e) => e.currentTarget.style.background = "rgba(197,150,58,0.12)"}
                    onMouseLeave={(e) => e.currentTarget.style.background = "rgba(27,58,92,0.3)"}
                  >
                    {p}
                  </button>
                ))}
              </div>

              <form onSubmit={handleSubmit} className="space-y-3">
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Введіть запит..."
                  rows={4}
                  className="w-full rounded-lg px-3 py-2 text-sm resize-none focus:outline-none"
                  style={{ background: "rgba(27,58,92,0.3)", color: "#E0E8F0", border: "1px solid rgba(27,58,92,0.4)" }}
                  onFocus={(e) => e.target.style.borderColor = "#C5963A"}
                  onBlur={(e) => e.target.style.borderColor = "rgba(27,58,92,0.4)"}
                />

                <div>
                  <label className="text-xs mb-1 block" style={{ color: "#5A7A9A" }}>JWT Token (опційно)</label>
                  <input
                    type="text"
                    value={agentToken}
                    onChange={(e) => setAgentToken(e.target.value)}
                    placeholder="Bearer token..."
                    className="w-full rounded-lg px-3 py-2 text-xs font-mono focus:outline-none"
                    style={{ background: "rgba(27,58,92,0.3)", color: "#E0E8F0", border: "1px solid rgba(27,58,92,0.4)" }}
                  />
                  <p className="text-xs mt-1" style={{ color: "#1B3A5C" }}>
                    Без токена → автоматично L2 (Fallback E6)
                  </p>
                </div>

                <button
                  type="submit"
                  disabled={loading || !prompt.trim()}
                  className="w-full py-2.5 rounded-lg font-semibold text-sm transition-all"
                  style={{
                    background: loading || !prompt.trim() ? "rgba(27,58,92,0.3)" : "#C5963A",
                    color: loading || !prompt.trim() ? "#5A7A9A" : "#0C1824",
                    cursor: loading || !prompt.trim() ? "not-allowed" : "pointer",
                  }}
                >
                  {loading ? "Генерація..." : "Запустити"}
                </button>
              </form>
            </div>

            {/* Agent metrics */}
            {result && (
              <div className="rounded-xl p-5" style={{ background: "rgba(27,58,92,0.12)", border: "1px solid rgba(27,58,92,0.35)" }}>
                <h3 className="font-semibold mb-3 text-xs uppercase tracking-wider" style={{ color: "#5A7A9A" }}>
                  Агент
                </h3>
                <div className="space-y-2 text-sm">
                  <MetaRow label="Рівень" value={result.agent_level} color="#C5963A" />
                  <MetaRow
                    label="Середній trust"
                    value={(avgTrust * 100).toFixed(1) + "%"}
                    color={avgTrust > 0.8 ? "#2E7D32" : avgTrust > 0.5 ? "#F9A825" : "#CC0000"}
                  />
                  {result.summary && (
                    <>
                      <MetaRow
                        label="Чистота ліцензій"
                        value={(result.summary.license_purity * 100).toFixed(1) + "%"}
                        color="#5A7A9A"
                      />
                      <MetaRow
                        label="High trust токени"
                        value={(result.summary.high_trust_ratio * 100).toFixed(1) + "%"}
                        color="#2E7D32"
                      />
                    </>
                  )}
                </div>
              </div>
            )}

            {error && (
              <div className="rounded-xl p-4 text-sm" style={{ background: "rgba(204,0,0,0.1)", border: "1px solid rgba(204,0,0,0.3)", color: "#CC0000" }}>
                {error}
              </div>
            )}
          </div>

          {/* Center: Token viewer */}
          <div className="lg:col-span-1">
            <div className="rounded-xl p-5 h-full" style={{ background: "rgba(27,58,92,0.12)", border: "1px solid rgba(27,58,92,0.35)" }}>
              <h3 className="font-serif font-semibold mb-4" style={{ color: "#C5963A" }}>
                Відповідь з провенансом
              </h3>
              {loading && (
                <div className="flex items-center gap-2 text-sm pt-4" style={{ color: "#5A7A9A" }}>
                  <div className="animate-spin w-4 h-4 rounded-full border-2"
                       style={{ borderColor: "#C5963A", borderTopColor: "transparent" }} />
                  Генерація з відстеженням провенансу...
                </div>
              )}
              {result && !loading ? (
                <TokenViewer tokens={result.tokens} />
              ) : !loading ? (
                <div className="text-sm text-center pt-16" style={{ color: "#1B3A5C" }}>
                  Введіть запит і натисніть «Запустити»
                </div>
              ) : null}
            </div>
          </div>

          {/* Right: Manifest + Chain */}
          <div className="lg:col-span-1 space-y-4">
            <ManifestPanel
              sessionId={result?.session_id}
              summary={result?.summary}
              tokens={result?.tokens}
            />
            <ChainViewer />
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t mt-16 py-8 text-center" style={{ borderColor: "rgba(27,58,92,0.3)" }}>
        <img src="/babyloooooon.png" alt="Babylooooooon.ai" className="h-6 w-auto mx-auto mb-3 opacity-50" />
        <p className="tagline text-xs" style={{ color: "#5A7A9A" }}>where every token knows its origin</p>
      </footer>
    </div>
  );
}

function MetaRow({ label, value, color = "#E0E8F0" }) {
  return (
    <div className="flex justify-between items-center py-1 border-b"
         style={{ borderColor: "rgba(27,58,92,0.3)" }}>
      <span style={{ color: "#5A7A9A" }}>{label}</span>
      <span className="font-mono font-semibold text-sm" style={{ color }}>{value}</span>
    </div>
  );
}
