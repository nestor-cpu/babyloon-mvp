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

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — leading-space preservation", () => {

  it("token ' Hello' renders textContent that starts with a space", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    const [span] = getTokenSpans(container);
    // textContent = token.text + inner dot-span's content (empty)
    expect(span.textContent).toBe(" Hello");
  });

  it("token ' How' renders textContent that starts with a space", () => {
    const { container } = render(<TokenViewer tokens={[tok(" How")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).toBe(" How");
  });

  it("continuation token 'ness' renders without a leading space", () => {
    const { container } = render(<TokenViewer tokens={[tok("ness")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).toBe("ness");
    expect(span.textContent.startsWith(" ")).toBe(false);
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — copy-paste concatenation", () => {

  it("concatenating token.text values preserves spaces: ' Hello' + '!' + ' How'", () => {
    const tokens = [tok(" Hello"), tok("!"), tok(" How")];
    const joined = tokens.map(t => t.text).join("");
    expect(joined).toBe(" Hello! How");
  });

  it("DOM spans preserve leading spaces so user selection gives correct text", () => {
    const tokens = [tok(" Hello"), tok("!"), tok(" How")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    const spans = getTokenSpans(container);

    // Each span's textContent must match token.text exactly.
    expect(spans[0].textContent).toBe(" Hello");
    expect(spans[1].textContent).toBe("!");
    expect(spans[2].textContent).toBe(" How");

    // Concatenation of textContents == concatenation of original token.text values.
    const domText  = spans.map(s => s.textContent).join("");
    const rawText  = tokens.map(t => t.text).join("");
    expect(domText).toBe(rawText);        // " Hello! How"
    expect(domText).toBe(" Hello! How");
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — no stripping of whitespace", () => {

  it("does not trim the leading space from ' can'", () => {
    const { container } = render(<TokenViewer tokens={[tok(" can")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).not.toBe("can");
    expect(span.textContent).toBe(" can");
  });

  it("renders an empty/falsy token as a single space fallback", () => {
    const { container } = render(<TokenViewer tokens={[tok("")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent).toBe(" "); // {token.text || " "}
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — white-space: pre-wrap on token spans", () => {

  it("each token span has whiteSpace='pre-wrap'", () => {
    const { container } = render(
      <TokenViewer tokens={[tok(" Hello"), tok("!"), tok(" How")]} />,
    );
    const spans = getTokenSpans(container);
    for (const span of spans) {
      expect(span.style.whiteSpace).toBe("pre-wrap");
    }
  });

  it("▁ prefix is replaced with a regular space in display text", () => {
    const { container } = render(<TokenViewer tokens={[tok("▁Hello")]} />);
    const [span] = getTokenSpans(container);
    // ▁ → " ", so textContent starts with a regular space
    expect(span.textContent).toBe(" Hello");
    expect(span.textContent.startsWith("▁")).toBe(false);
  });

  it("continuation token has no leading space", () => {
    const { container } = render(<TokenViewer tokens={[tok("ness")]} />);
    const [span] = getTokenSpans(container);
    expect(span.textContent.startsWith(" ")).toBe(false);
  });

});
