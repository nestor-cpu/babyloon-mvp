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

export default function Syaivo() {
  const [prompt, setPrompt] = useState("");
  const [agentToken, setAgentToken] = useState("");
  const [agentLevel, setAgentLevel] = useState("L2");
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

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center gap-4">
        <div className="text-2xl font-bold">
          <span className="text-yellow-400">С</span>яйво
          <span className="text-gray-500 text-sm ml-3 font-normal">
            + babyl<span className="text-indigo-400">∞</span>n.ai
          </span>
        </div>
        <div className="ml-auto text-xs text-gray-500 font-mono">
          Демонстрація для Мінцифри України
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Intro */}
        <div className="bg-blue-950/40 border border-blue-800 rounded-xl p-6 mb-8">
          <h2 className="text-lg font-bold text-blue-300 mb-2">
            Провенанс для національної LLM «Сяйво»
          </h2>
          <p className="text-gray-300 text-sm leading-relaxed">
            Ця сторінка демонструє, як babyloon.ai додає прозорість до україномовних LLM.
            Кожне слово у відповіді прив'язане до конкретного джерела — українські датасети,
            вікіпедія, академічні тексти. Атрибуція в реальному часі.
          </p>
        </div>

        <div className="grid lg:grid-cols-3 gap-6">
          {/* Left: Input */}
          <div className="lg:col-span-1 space-y-4">
            <div className="bg-gray-900 rounded-xl p-5">
              <h3 className="font-semibold mb-4 text-yellow-400">Запит</h3>

              {/* Sample prompts */}
              <div className="mb-4 space-y-2">
                <p className="text-xs text-gray-500 mb-2">Приклади запитів:</p>
                {SAMPLE_PROMPTS_UK.map((p) => (
                  <button
                    key={p}
                    onClick={() => setPrompt(p)}
                    className="w-full text-left text-xs bg-gray-800 hover:bg-gray-700 rounded-lg px-3 py-2 text-gray-300 transition-colors"
                  >
                    {p}
                  </button>
                ))}
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Введіть запит українською мовою..."
                  rows={4}
                  className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-yellow-500 placeholder-gray-600"
                />

                <div>
                  <label className="text-xs text-gray-400 mb-1 block">JWT Token (опційно)</label>
                  <input
                    type="text"
                    value={agentToken}
                    onChange={(e) => setAgentToken(e.target.value)}
                    placeholder="Bearer token..."
                    className="w-full bg-gray-800 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-yellow-500 placeholder-gray-600"
                  />
                  <p className="text-xs text-gray-600 mt-1">
                    Без токена → автоматично L2 (Fallback E6)
                  </p>
                </div>

                <button
                  type="submit"
                  disabled={loading || !prompt.trim()}
                  className="w-full py-2 bg-yellow-600 hover:bg-yellow-500 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg font-semibold text-sm transition-colors"
                >
                  {loading ? "Генерація..." : "Запустити"}
                </button>
              </form>
            </div>

            {/* Agent info */}
            {result && (
              <div className="bg-gray-900 rounded-xl p-5">
                <h3 className="font-semibold mb-3 text-xs text-gray-400 uppercase tracking-wider">
                  Агент
                </h3>
                <div className="space-y-2 text-sm">
                  <Row label="Рівень" value={result.agent_level} color="text-yellow-400" />
                  {(() => {
                    const toks = result.tokens ?? [];
                    const avg = toks.length
                      ? toks.reduce((s, t) => s + (t.trust_avg ?? 0), 0) / toks.length
                      : 0;
                    return (
                      <Row
                        label="Середній trust"
                        value={(avg * 100).toFixed(1) + "%"}
                        color={avg > 0.8 ? "text-green-400" : avg > 0.5 ? "text-yellow-400" : "text-red-400"}
                      />
                    );
                  })()}
                  {result.summary && (
                    <>
                      <Row
                        label="Чистота ліцензій"
                        value={(result.summary.license_purity * 100).toFixed(1) + "%"}
                        color="text-blue-400"
                      />
                      <Row
                        label="High trust токени"
                        value={(result.summary.high_trust_ratio * 100).toFixed(1) + "%"}
                        color="text-green-400"
                      />
                    </>
                  )}
                </div>
              </div>
            )}

            {error && (
              <div className="bg-red-950/40 border border-red-800 rounded-xl p-4 text-sm text-red-300">
                {error}
              </div>
            )}
          </div>

          {/* Center: Token viewer */}
          <div className="lg:col-span-1">
            <div className="bg-gray-900 rounded-xl p-5 h-full">
              <h3 className="font-semibold mb-4 text-yellow-400">
                Відповідь з провенансом
              </h3>
              {result ? (
                <TokenViewer tokens={result.tokens} />
              ) : (
                <div className="text-gray-600 text-sm text-center pt-16">
                  Введіть запит і натисніть «Запустити»
                </div>
              )}
            </div>
          </div>

          {/* Right: Manifest + Chain */}
          <div className="lg:col-span-1 space-y-4">
            <ManifestPanel sessionId={result?.session_id} summary={result?.summary} />
            <ChainViewer />
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, color = "text-white" }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className={`font-mono font-semibold ${color}`}>{value}</span>
    </div>
  );
}
