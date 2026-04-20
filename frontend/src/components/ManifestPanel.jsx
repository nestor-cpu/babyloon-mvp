/**
 * ManifestPanel — E4: Live provenance manifest viewer
 * Shows JSONL stream of token records + aggregate summary.
 *
 * Props:
 *   sessionId: string
 *   summary: session summary dict
 *   tokens: token_provenances array
 */
export default function ManifestPanel({ sessionId, summary, tokens = [] }) {
  return (
    <div className="bg-gray-900 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Live Manifest (E4)
        </h3>
        {sessionId && (
          <span className="text-xs font-mono text-gray-600 truncate max-w-32">
            {sessionId.slice(0, 8)}…
          </span>
        )}
      </div>

      {/* Aggregate metrics */}
      {summary && (
        <div className="grid grid-cols-2 gap-2 mb-4">
          <Metric
            label="License Purity"
            value={(summary.license_purity * 100).toFixed(1) + "%"}
            color={summary.license_purity > 0.8 ? "text-green-400" : "text-yellow-400"}
          />
          <Metric
            label="High Trust"
            value={(summary.high_trust_ratio * 100).toFixed(1) + "%"}
            color={summary.high_trust_ratio > 0.7 ? "text-green-400" : "text-yellow-400"}
          />
          <Metric label="Tokens" value={summary.total_tokens} />
          <Metric
            label="Sources"
            value={summary.dominant_sources?.length ?? 0}
          />
        </div>
      )}

      {/* Dominant sources */}
      {summary?.dominant_sources?.length > 0 && (
        <div className="mb-4">
          <p className="text-xs text-gray-500 mb-2">Top Sources</p>
          <div className="space-y-1">
            {summary.dominant_sources.map((src, i) => (
              <div key={i} className="flex items-center gap-2">
                <div
                  className="h-1.5 bg-indigo-500 rounded-full"
                  style={{ width: `${Math.round(src.total_weight * 100)}%`, maxWidth: "100%" }}
                />
                <span className="text-xs text-gray-400 truncate flex-1">
                  {src.source_name || src.segment_id?.slice(0, 12)}
                </span>
                <span className="text-xs font-mono text-gray-500">
                  {(src.total_weight * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* JSONL stream — last 8 records */}
      <div>
        <p className="text-xs text-gray-500 mb-2">JSONL Stream</p>
        <div className="bg-gray-950 rounded-lg p-2 h-40 overflow-y-auto font-mono text-xs space-y-0.5">
          {tokens.length === 0 ? (
            <span className="text-gray-700">Waiting for tokens...</span>
          ) : (
            tokens.slice(-12).map((t, i) => (
              <div key={i} className="flex gap-2 items-start">
                <span className="text-gray-700 w-4 text-right flex-shrink-0">{t.position}</span>
                <span
                  className={
                    (t.trust_avg ?? 0) >= 0.8
                      ? "text-green-400"
                      : (t.trust_avg ?? 0) >= 0.5
                      ? "text-yellow-400"
                      : "text-red-400"
                  }
                >
                  {JSON.stringify({
                    t: t.text,
                    trust: t.trust_avg?.toFixed(2),
                    src: t.attribution?.[0]?.source_name?.slice(0, 12),
                  })}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, color = "text-white" }) {
  return (
    <div className="bg-gray-800 rounded-lg p-2 text-center">
      <div className={`font-mono font-bold text-sm ${color}`}>{value}</div>
      <div className="text-xs text-gray-500 mt-0.5">{label}</div>
    </div>
  );
}
