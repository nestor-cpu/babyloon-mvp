import { useState } from "react";

/**
 * TokenViewer — renders model output token-by-token, color-coded by trust score.
 * Expert View: each token is a highlighted pill.
 * Hover on any token → popup with source, weight, license, trust score.
 *
 * Layout strategy — fontSize:0 container + flatMap array render:
 *   • container fontSize:0  → kills any browser whitespace text nodes between spans
 *   • flatMap returns a plain JS array → React renders array items with zero
 *     injected whitespace (unlike JSX sibling elements which can produce "\n" nodes)
 *   • Word-start tokens (begin with " " or "▁" or "Ġ") get a selectable " " span
 *     before them — this is the ONLY source of inter-word space in the DOM
 *   • Continuation tokens (subwords, Cyrillic chars …) carry no horizontal padding
 *     and no preceding space → truly flush rendering
 *
 * Props:
 *   tokens: TokenProvenance[] from /generate response
 */
export default function TokenViewer({ tokens = [] }) {
  const [hoveredIdx, setHoveredIdx] = useState(null);
  const [popupPos, setPopupPos] = useState({ x: 0, y: 0 });

  if (!tokens.length) return null;

  // ── DEBUG: log first 20 tokens so we can inspect charCode(0) ────────────
  // Remove this block once the spacing issue is fully confirmed / resolved.
  if (import.meta.env.DEV && tokens.length > 0) {
    const sample = tokens.slice(0, 20);
    console.log(
      "[TokenViewer] first tokens (text / charCode0 / isWordStart):\n" +
      sample.map((t, i) => {
        const raw = t.text ?? "";
        const cc  = raw.length > 0 ? raw.charCodeAt(0) : -1;
        const ws  = raw.length > 0 && isWordStartChar(cc);
        return `  [${i}] "${raw}" | cc0=${cc} (0x${cc.toString(16).toUpperCase()}) | wordStart=${ws}`;
      }).join("\n"),
    );
  }
  // ────────────────────────────────────────────────────────────────────────

  function getTrustColor(trust) {
    if (trust >= 0.8) return "bg-green-900/40 border-green-700/50 text-green-100";
    if (trust >= 0.5) return "bg-yellow-900/30 border-yellow-700/40 text-yellow-100";
    return "bg-red-900/30 border-red-700/40 text-red-100";
  }

  function getTrustDot(trust) {
    if (trust >= 0.8) return "bg-green-400";
    if (trust >= 0.5) return "bg-yellow-400";
    return "bg-red-400";
  }

  const POPUP_W = 292;
  const POPUP_H = 300;
  const MARGIN  = 8;

  function handleMouseEnter(idx, e) {
    setHoveredIdx(idx);
    setPopupPos({ x: e.clientX, y: e.clientY });
  }

  const hoveredToken = hoveredIdx !== null ? tokens[hoveredIdx] : null;

  const popupLeft = Math.min(
    popupPos.x + 12,
    window.innerWidth - POPUP_W - MARGIN,
  );
  const popupTop =
    popupPos.y + 16 + POPUP_H > window.innerHeight
      ? Math.max(MARGIN, popupPos.y - POPUP_H - 8)
      : popupPos.y + 16;

  function getLicensePurity(attribution = []) {
    const clean = new Set(["CC0", "public-domain", "Apache-2.0", "MIT", "CC-BY", "CC-BY-SA"]);
    const totalW = attribution.reduce((s, a) => s + (a.weight ?? 0), 0);
    if (totalW === 0) return 0;
    const cleanW = attribution
      .filter((a) => clean.has(a.license_class))
      .reduce((s, a) => s + (a.weight ?? 0), 0);
    return cleanW / totalW;
  }

  // Shared style for every span (pill + space-node): restores font-size wiped
  // by the fontSize:0 trick on the container.
  const SPAN_STYLE = { fontSize: "14px", display: "inline", userSelect: "text" };

  // Build the flat element array via flatMap so React renders items with zero
  // injected whitespace — unlike JSX siblings which may produce "\n  " text nodes.
  const pillElements = tokens.flatMap((token, idx) => {
    const trust      = token.trust_avg ?? 0;
    const colorClass = getTrustColor(trust);
    const dotClass   = getTrustDot(trust);

    const raw = token.text ?? "";

    // ── Word-start detection ─────────────────────────────────────────────
    // Covers every tokenizer that may reach this component:
    //   U+0020  ' '   ASCII space — Mistral after backend ▁→space replace
    //   U+2581  '▁'   SentencePiece raw prefix (fallback, should not occur)
    //   U+0120  'Ġ'   GPT-2 / RoBERTa BPE word-boundary marker
    //   U+010A  'Ċ'   GPT-2 BPE newline marker (treat as word-start)
    const cc0        = raw.length > 0 ? raw.charCodeAt(0) : -1;
    const isWordStart = isWordStartChar(cc0);

    // Strip exactly one leading separator for the pill label.
    const display = isWordStart ? raw.slice(1) : raw;

    const hoverClass = hoveredIdx === idx ? "ring-1 ring-white/40 scale-105" : "";

    // Word-start pills get a little breathing room; continuation pills are
    // padding-free so adjacent subword/Cyrillic chars appear truly flush.
    const hPad = isWordStart ? "px-0.5" : "";

    const dot = (
      <span
        key={`dot-${idx}`}
        className={`absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full ${dotClass}`}
      />
    );

    const pill = (
      <span
        key={`p-${idx}`}
        className={`token-pill relative cursor-default ${hPad} py-0.5 rounded border transition-all duration-150 ${colorClass} ${hoverClass}`}
        style={SPAN_STYLE}
        onMouseEnter={(e) => handleMouseEnter(idx, e)}
        onMouseLeave={() => setHoveredIdx(null)}
      >{display || "​"}{dot}</span>
    );

    if (isWordStart && idx > 0) {
      // Selectable space span — copy-paste preserves inter-word spacing.
      const spacer = <span key={`sp-${idx}`} style={SPAN_STYLE}>{" "}</span>;
      return [spacer, pill];
    }

    return [pill];
  });

  return (
    <div className="relative">
      {/* Token stream ──────────────────────────────────────────────────────
          fontSize:0 kills browser whitespace between inline children.
          pillElements is a flat JS array — no JSX sibling whitespace.    */}
      <div
        data-testid="token-stream"
        className="leading-relaxed"
        style={{ fontSize: 0 }}
      >{pillElements}</div>

      {/* Hover popup */}
      {hoveredToken && hoveredToken.attribution?.length > 0 && (
        <div
          className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl p-4 text-sm pointer-events-none"
          style={{
            position: "fixed",
            zIndex:   9999,
            top:      popupTop,
            left:     popupLeft,
            width:    POPUP_W,
          }}
        >
          <div className="font-mono text-gray-400 text-xs mb-2">
            Token: <span className="text-white font-semibold">"{hoveredToken.text}"</span>
            <span className="ml-2 text-gray-600">pos={hoveredToken.position}</span>
          </div>

          <div className="mb-2">
            <TrustBadge trust={hoveredToken.trust_avg} />
            <span className="text-xs text-gray-500 ml-2">
              license purity {(getLicensePurity(hoveredToken.attribution) * 100).toFixed(0)}%
            </span>
          </div>

          <div className="space-y-2">
            {hoveredToken.attribution.map((attr, i) => (
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
                  <TrustBadge trust={attr.trust_score} small />
                </div>
              </div>
            ))}
          </div>

          {hoveredToken.attribution?.[0] && (
            <div className="mt-2 text-xs text-gray-600 font-mono truncate">
              seg: {hoveredToken.attribution[0].segment_id}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Returns true if the character code at position 0 of a token's raw text
 * indicates a word-boundary (the token starts a new word).
 *
 * Known markers across tokenizer families:
 *   0x0020  ' '  ASCII space   — Mistral/LLaMA after backend ▁→space decode
 *   0x2581  '▁'  SentencePiece — raw prefix, should not reach frontend normally
 *   0x0120  'Ġ'  GPT-2 BPE     — word-boundary glyph used by RoBERTa etc.
 *   0x010A  'Ċ'  GPT-2 BPE     — newline marker (treat as word-start)
 */
function isWordStartChar(cc0) {
  return cc0 === 0x0020   // ' '
      || cc0 === 0x2581   // '▁'
      || cc0 === 0x0120   // 'Ġ'
      || cc0 === 0x010A;  // 'Ċ'
}

function TrustBadge({ trust, small }) {
  const val = trust ?? 0;
  const color =
    val >= 0.8 ? "bg-green-900/60 text-green-300 border-green-700" :
    val >= 0.5 ? "bg-yellow-900/60 text-yellow-300 border-yellow-700" :
    "bg-red-900/60 text-red-300 border-red-700";
  return (
    <span className={`border rounded px-1.5 py-0.5 font-mono ${color} ${small ? "text-xs" : "text-xs"}`}>
      trust {(val * 100).toFixed(0)}%
    </span>
  );
}
