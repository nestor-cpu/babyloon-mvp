import { useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

/**
 * ChainViewer — E5: Hash-chain visualization + verify button
 */
export default function ChainViewer() {
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState(null);
  const [records, setRecords] = useState([]);
  const [loadingRecords, setLoadingRecords] = useState(false);

  async function handleVerify() {
    setVerifying(true);
    setVerifyResult(null);
    try {
      const res = await fetch(`${API}/registry/verify`);
      const data = await res.json();
      setVerifyResult(data);
    } catch (err) {
      setVerifyResult({ valid: false, message: err.message });
    } finally {
      setVerifying(false);
    }
  }

  async function handleLoadRecords() {
    setLoadingRecords(true);
    try {
      const res = await fetch(`${API}/registry`);
      if (!res.ok) {
        // 403 if not L0 — show partial info
        setRecords([{ id: "...", type: "restricted", record_hash: "L1+ required" }]);
        return;
      }
      const data = await res.json();
      setRecords(data.slice(-5)); // last 5
    } catch (err) {
      setRecords([]);
    } finally {
      setLoadingRecords(false);
    }
  }

  return (
    <div className="bg-gray-900 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Hash-Chain Registry (E5)
        </h3>
      </div>

      {/* Chain visualization */}
      <div className="mb-4 space-y-1">
        {records.length > 0 ? (
          records.map((rec, i) => (
            <ChainBlock key={rec.id} record={rec} isFirst={i === 0} />
          ))
        ) : (
          <div className="flex gap-2 items-center">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="flex items-center gap-1">
                <div className="w-8 h-8 rounded-lg bg-gray-800 border border-gray-700 flex items-center justify-center">
                  <span className="text-xs text-gray-600 font-mono">{i + 1}</span>
                </div>
                {i < 4 && <div className="text-gray-700 text-xs">→</div>}
              </div>
            ))}
            <span className="text-xs text-gray-600 ml-1">…</span>
          </div>
        )}
      </div>

      {/* Verify result */}
      {verifyResult && (
        <div
          className={`mb-3 px-3 py-2 rounded-lg text-sm font-semibold flex items-center gap-2 ${
            verifyResult.valid
              ? "bg-green-950/50 border border-green-800 text-green-300"
              : "bg-red-950/50 border border-red-800 text-red-300"
          }`}
        >
          <span>{verifyResult.valid ? "✓" : "✗"}</span>
          <span>{verifyResult.message}</span>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        <button
          onClick={handleVerify}
          disabled={verifying}
          className="flex-1 py-1.5 text-xs bg-indigo-700 hover:bg-indigo-600 disabled:bg-gray-800 disabled:text-gray-600 rounded-lg font-semibold transition-colors"
        >
          {verifying ? "Verifying..." : "Verify Chain"}
        </button>
        <button
          onClick={handleLoadRecords}
          disabled={loadingRecords}
          className="flex-1 py-1.5 text-xs border border-gray-700 hover:border-gray-500 disabled:text-gray-600 rounded-lg transition-colors"
        >
          {loadingRecords ? "Loading..." : "View Records"}
        </button>
      </div>
    </div>
  );
}

function ChainBlock({ record, isFirst }) {
  const hash = record.record_hash || "";
  const shortHash = hash.slice(0, 8) + "…";
  const typeColor =
    record.type === "corpus_segment" ? "border-blue-700 bg-blue-950/30" :
    record.type === "inference" ? "border-purple-700 bg-purple-950/30" :
    "border-gray-700 bg-gray-800";

  return (
    <div className="flex items-start gap-2">
      {!isFirst && <div className="w-3 text-gray-700 text-xs mt-1 flex-shrink-0">↑</div>}
      {isFirst && <div className="w-3 flex-shrink-0" />}
      <div className={`flex-1 rounded-lg border px-2 py-1.5 ${typeColor}`}>
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-gray-400">{record.type}</span>
          <span className="text-xs font-mono text-gray-600">{shortHash}</span>
        </div>
        <div className="text-xs text-gray-600 mt-0.5 font-mono truncate">
          prev: {(record.prev_hash || "").slice(0, 8)}…
        </div>
      </div>
    </div>
  );
}
