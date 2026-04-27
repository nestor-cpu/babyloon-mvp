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
 * Returns all direct-child spans of the token stream flex container
 * (the coloured token pills — every token is a single flex item).
 */
function getTokenSpans(container) {
  const stream = container.querySelector("[style*='flex-wrap']");
  return Array.from(stream.querySelectorAll(":scope > span"));
}

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — word-start vs continuation pill content", () => {

  it("word-start token ' Hello': pill textContent is 'Hello' (leading space stripped)", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).toBe("Hello");
  });

  it("word-start token ' How': pill textContent is 'How'", () => {
    const { container } = render(<TokenViewer tokens={[tok(" How")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).toBe("How");
  });

  it("continuation token 'ness': pill textContent is 'ness' (no leading space)", () => {
    const { container } = render(<TokenViewer tokens={[tok("ness")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).toBe("ness");
    expect(span.textContent.startsWith(" ")).toBe(false);
  });

  it("continuation token 'ificial': textContent is 'ificial' (no space)", () => {
    const { container } = render(<TokenViewer tokens={[tok("ificial")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).toBe("ificial");
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — flexbox marginLeft spacing", () => {

  it("first token (idx=0) has marginLeft=0 regardless of word-start", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    const [span] = getTokenSpans(container);
    // First token never gets a left margin.
    const ml = span.style.marginLeft;
    expect(ml === "" || ml === "0px" || ml === "0").toBe(true);
  });

  it("second word-start token has marginLeft='0.25em'", () => {
    const tokens = [tok(" Hello"), tok(" World")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    const spans = getTokenSpans(container);
    expect(spans[1].style.marginLeft).toBe("0.25em");
  });

  it("continuation token has marginLeft=0 (flush with previous pill)", () => {
    const tokens = [tok(" Art"), tok("ificial")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    const spans = getTokenSpans(container);
    const ml = spans[1].style.marginLeft;
    expect(ml === "" || ml === "0px" || ml === "0").toBe(true);
  });

  it("▁ prefix token at idx>0 has marginLeft='0.25em'", () => {
    const tokens = [tok("Hello"), tok("▁World")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    const spans = getTokenSpans(container);
    expect(spans[1].style.marginLeft).toBe("0.25em");
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — token count and structure", () => {

  it("renders exactly one span per token", () => {
    const tokens = [tok(" Hello"), tok("!"), tok(" How")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    const spans = getTokenSpans(container);
    expect(spans).toHaveLength(3);
  });

  it("'Art' + 'ificial' renders 2 spans, not 3 (no extra whitespace node span)", () => {
    const tokens = [tok(" Art"), tok("ificial")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    const spans = getTokenSpans(container);
    expect(spans).toHaveLength(2);
  });

  it("continuation subword pills have zero left margin (no CSS gap injected)", () => {
    const tokens = [tok(" trans"), tok("par"), tok("ency")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    const spans = getTokenSpans(container);
    // "par" and "ency" are continuations — marginLeft must be 0
    for (const span of [spans[1], spans[2]]) {
      const ml = span.style.marginLeft;
      expect(ml === "" || ml === "0px" || ml === "0").toBe(true);
    }
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — special token display", () => {

  it("▁ prefix is stripped from display: '▁Hello' → pill shows 'Hello'", () => {
    const { container } = render(<TokenViewer tokens={[tok("▁Hello")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).toBe("Hello");
    expect(span.textContent.startsWith("▁")).toBe(false);
  });

  it("empty token renders a zero-width space (keeps pill visible)", () => {
    const { container } = render(<TokenViewer tokens={[tok("")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).toBe("​"); // zero-width space U+200B
  });

  it("token.text concatenation preserves the original spacing", () => {
    const tokens = [tok(" Hello"), tok("!"), tok(" How")];
    const joined = tokens.map(t => t.text).join("");
    expect(joined).toBe(" Hello! How");
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — flex container layout", () => {

  it("stream container uses flex layout with flex-wrap", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    const stream = container.querySelector("[style*='flex-wrap']");
    expect(stream).not.toBeNull();
    expect(stream.style.display).toBe("flex");
    expect(stream.style.flexWrap).toBe("wrap");
  });

  it("stream container aligns items to baseline", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    const stream = container.querySelector("[style*='flex-wrap']");
    expect(stream.style.alignItems).toBe("baseline");
  });

});
