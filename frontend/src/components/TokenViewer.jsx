import { useState, Fragment } from "react";

/**
 * TokenViewer — renders model output token-by-token, color-coded by trust score.
 * Expert View: each token is a highlighted pill.
 * Hover on any token → popup with source, weight, license, trust score.
 *
 * Layout strategy — fontSize:0 container:
 *   The container font-size is set to 0 to kill any browser-injected whitespace
 *   between adjacent inline elements (caused by JSX newlines / HTML source gaps).
 *   Every token pill restores font-size to 14px via inline style.
 *
 *   Inter-word spacing is a plain " " inside a dedicated <span> rendered only for
 *   word-start tokens (those whose raw text begins with " " or "▁"). This span is
 *   selectable, so Ctrl+C copy-paste preserves word spacing.
 *
 *   Continuation tokens (Cyrillic individual chars, Latin subwords) carry NO
 *   horizontal padding — they render flush to the neighbouring pill so "проєкт"
 *   tokenised as ['п','р','о','є','к','т'] displays as a single highlighted block,
 *   not six space-separated characters.
 *
 * Props:
 *   tokens: TokenProvenance[] from /generate response
 */
export default function TokenViewer({ tokens = [] }) {
  const [hoveredIdx, setHoveredIdx] = useState(null);
  const [popupPos, setPopupPos] = useState({ x: 0, y: 0 });

  if (!tokens.length) return null;

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

  // Shared inline style applied to every rendered span so fontSize:0 on the
  // container doesn't bleed into the pills / space nodes.
  const SPAN_STYLE = { fontSize: "14px", display: "inline", userSelect: "text" };

  return (
    <div className="relative">
      {/* Token stream ─────────────────────────────────────────────────────
          fontSize:0 on the container eliminates all whitespace text nodes that
          browsers inject between inline elements due to JSX source formatting.
          Each child span restores its own font size explicitly.           */}
      <div
        data-testid="token-stream"
        className="leading-relaxed"
        style={{ fontSize: 0 }}
      >
        {tokens.map((token, idx) => {
          const trust = token.trust_avg ?? 0;
          const colorClass = getTrustColor(trust);
          const dotClass   = getTrustDot(trust);

          const raw = token.text ?? "";

          // Word-start: token begins with " " (Mistral) or "▁" (SentencePiece).
          // Continuation: no leading whitespace — renders flush to previous pill.
          const isWordStart = raw.startsWith(" ") || raw.startsWith("▁");

          // Strip the leading separator for the visual pill label.
          const display = isWordStart ? raw.replace(/^[ ▁]/, "") : raw;

          const hoverClass = hoveredIdx === idx ? "ring-1 ring-white/40 scale-105" : "";

          // Horizontal padding only on word-start pills (gives them breathing room).
          // Continuation pills have no px-padding so adjacent chars are truly flush.
          const hPad = isWordStart ? "px-0.5" : "";

          const dot = (
            <span className={`absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full ${dotClass}`} />
          );

          const pill = (
            <span
              className={`token-pill relative cursor-default ${hPad} py-0.5 rounded border transition-all duration-150 ${colorClass} ${hoverClass}`}
              style={SPAN_STYLE}
              onMouseEnter={(e) => handleMouseEnter(idx, e)}
              onMouseLeave={() => setHoveredIdx(null)}
            >
              {display || "​"}{/* zero-width space keeps pill visible for empty display */}
              {dot}
            </span>
          );

          if (isWordStart && idx > 0) {
            // Space is a selectable plain-text span — copy-paste preserves spacing.
            return (
              <Fragment key={idx}>
                <span style={SPAN_STYLE}>{" "}</span>
                {pill}
              </Fragment>
            );
          }

          // First token OR continuation — no preceding space span.
          return <Fragment key={idx}>{pill}</Fragment>;
        })}
      </div>

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
