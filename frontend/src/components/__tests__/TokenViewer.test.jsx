import { render } from "@testing-library/react";
import { describe, it, expect, beforeAll, vi } from "vitest";
import TokenViewer from "../TokenViewer";

// TokenViewer reads window dimensions for popup positioning.
beforeAll(() => {
  vi.stubGlobal("innerWidth",  1280);
  vi.stubGlobal("innerHeight", 800);
});

/** Minimal token fixture. attribution=[] suppresses the hover popup. */
function tok(text, trust = 0.85) {
  return { text, trust_avg: trust, position: 0, attribution: [] };
}

/**
 * Returns all direct-child spans of the token stream container
 * (i.e. the coloured token pills, not the dot inside each pill).
 */
function getTokenSpans(container) {
  const stream = container.querySelector(".leading-relaxed");
  return Array.from(stream.querySelectorAll(":scope > span"));
}

/**
 * Returns the full text content of the token stream div,
 * including text nodes between spans (the inter-word spaces).
 */
function getStreamText(container) {
  return container.querySelector(".leading-relaxed").textContent;
}

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — word-start vs continuation rendering", () => {

  it("word-start token ' Hello': span textContent is 'Hello' (space is a sibling text node)", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    const [span] = getTokenSpans(container);
    // The leading space is emitted as a text node BEFORE the span, not inside it.
    expect(span.textContent).toBe("Hello");
  });

  it("word-start token ' How': span textContent is 'How'", () => {
    const { container } = render(<TokenViewer tokens={[tok(" How")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).toBe("How");
  });

  it("continuation token 'ness' renders without a leading space", () => {
    const { container } = render(<TokenViewer tokens={[tok("ness")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).toBe("ness");
    expect(span.textContent.startsWith(" ")).toBe(false);
  });

  it("word-start token has inline-block class", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    const [span] = getTokenSpans(container);
    expect(span.className).toContain("inline-block");
  });

  it("continuation token has inline class (not inline-block)", () => {
    const { container } = render(<TokenViewer tokens={[tok("ness")]} />);
    const [span] = getTokenSpans(container);
    expect(span.className).toContain("inline");
    expect(span.className).not.toContain("inline-block");
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — copy-paste concatenation", () => {

  it("concatenating token.text values preserves spaces: ' Hello' + '!' + ' How'", () => {
    const tokens = [tok(" Hello"), tok("!"), tok(" How")];
    const joined = tokens.map(t => t.text).join("");
    expect(joined).toBe(" Hello! How");
  });

  it("stream div textContent includes inter-word spaces from text nodes", () => {
    const tokens = [tok(" Hello"), tok("!"), tok(" How")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    // The stream's full textContent includes the " " text nodes emitted before
    // each word-start token (idx > 0). dot-spans have no text content.
    // Result: "Hello" + "!" + " " + "How" = "Hello! How"
    expect(getStreamText(container)).toBe("Hello! How");
  });

  it("continuation subword 'trans'+'parency' — spans are flush, stream text is 'transparency'", () => {
    const tokens = [tok("trans"), tok("parency")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    expect(getStreamText(container)).toBe("transparency");
  });

  it("word + subword: ' show'+'case' → stream text is ' showcase'", () => {
    // idx=0 word-start has no preceding text node; idx=1 is continuation flush.
    const tokens = [tok(" show"), tok("case")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    // word-start span = "show", continuation span = "case"
    // No text node before idx=0 (idx > 0 is false), no space between them.
    expect(getStreamText(container)).toBe("showcase");
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — special token display", () => {

  it("does not trim the leading space from ' can' — span displays 'can'", () => {
    const { container } = render(<TokenViewer tokens={[tok(" can")]} />);
    const [span] = getTokenSpans(container);
    // Span displays stripped text; space is the sibling text node.
    expect(span.textContent).toBe("can");
  });

  it("renders an empty/falsy token span with zero-width space fallback", () => {
    const { container } = render(<TokenViewer tokens={[tok("")]} />);
    const [span] = getTokenSpans(container);
    // Empty display → zero-width space keeps pill visible.
    expect(span.textContent).toBe("​");
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — whitespace and ▁ handling", () => {

  it("each token span has whiteSpace='normal'", () => {
    const { container } = render(
      <TokenViewer tokens={[tok(" Hello"), tok("!"), tok(" How")]} />,
    );
    const spans = getTokenSpans(container);
    for (const span of spans) {
      expect(span.style.whiteSpace).toBe("normal");
    }
  });

  it("▁ prefix token is treated as word-start: span displays 'Hello' (no ▁)", () => {
    const { container } = render(<TokenViewer tokens={[tok("▁Hello")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).toBe("Hello");
    expect(span.textContent.startsWith("▁")).toBe(false);
    expect(span.textContent.startsWith(" ")).toBe(false);
  });

  it("▁ prefix token has inline-block class (word-start)", () => {
    const { container } = render(<TokenViewer tokens={[tok("▁Hello")]} />);
    const [span] = getTokenSpans(container);
    expect(span.className).toContain("inline-block");
  });

  it("continuation token has no leading space in textContent", () => {
    const { container } = render(<TokenViewer tokens={[tok("ness")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent.startsWith(" ")).toBe(false);
  });

});
