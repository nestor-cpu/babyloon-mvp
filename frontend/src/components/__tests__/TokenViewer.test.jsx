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

/** All .token-pill spans — one per token, excludes the space spans. */
function getPills(container) {
  return Array.from(container.querySelectorAll(".token-pill"));
}

/** The token stream container element. */
function getStream(container) {
  return container.querySelector("[data-testid='token-stream']");
}

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — container layout (fontSize:0 trick)", () => {

  it("stream container has fontSize 0 (kills browser whitespace between inline spans)", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    // React sets style.fontSize; jsdom normalises 0 → "0px".
    const fs = getStream(container).style.fontSize;
    expect(fs === "0" || fs === "0px").toBe(true);
  });

  it("every token pill has fontSize '14px' (restores readable size)", () => {
    const { container } = render(
      <TokenViewer tokens={[tok(" Hello"), tok("!"), tok(" World")]} />,
    );
    for (const pill of getPills(container)) {
      expect(pill.style.fontSize).toBe("14px");
    }
  });

  it("every token pill has display 'inline'", () => {
    const { container } = render(
      <TokenViewer tokens={[tok(" Hello"), tok("ness"), tok(" How")]} />,
    );
    for (const pill of getPills(container)) {
      expect(pill.style.display).toBe("inline");
    }
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — word-start vs continuation pill content", () => {

  it("word-start ' Hello' → pill textContent is 'Hello' (space stripped)", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    const [pill] = getPills(container);
    expect(pill.textContent).toBe("Hello");
  });

  it("continuation 'ness' → pill textContent is 'ness'", () => {
    const { container } = render(<TokenViewer tokens={[tok("ness")]} />);
    const [pill] = getPills(container);
    expect(pill.textContent).toBe("ness");
    expect(pill.textContent.startsWith(" ")).toBe(false);
  });

  it("Cyrillic continuation 'р' → pill textContent is 'р' (no leading space)", () => {
    const { container } = render(<TokenViewer tokens={[tok("р")]} />);
    const [pill] = getPills(container);
    expect(pill.textContent).toBe("р");
    expect(pill.textContent.startsWith(" ")).toBe(false);
  });

  it("▁ prefix stripped: '▁Hello' → pill textContent is 'Hello'", () => {
    const { container } = render(<TokenViewer tokens={[tok("▁Hello")]} />);
    const [pill] = getPills(container);
    expect(pill.textContent).toBe("Hello");
    expect(pill.textContent.startsWith("▁")).toBe(false);
  });

  it("empty token → pill shows zero-width space (pill stays visible)", () => {
    const { container } = render(<TokenViewer tokens={[tok("")]} />);
    const [pill] = getPills(container);
    expect(pill.textContent).toBe("​"); // U+200B zero-width space
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — horizontal padding rules", () => {

  it("word-start pill has px-0.5 class (horizontal breathing room)", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    const [pill] = getPills(container);
    expect(pill.className).toContain("px-0.5");
  });

  it("continuation pill does NOT have px-0.5 (renders flush, no Cyrillic gaps)", () => {
    const { container } = render(<TokenViewer tokens={[tok("р")]} />);
    const [pill] = getPills(container);
    expect(pill.className).not.toContain("px-0.5");
  });

  it("subword continuation 'ificial' has no px-0.5", () => {
    const { container } = render(<TokenViewer tokens={[tok("ificial")]} />);
    const [pill] = getPills(container);
    expect(pill.className).not.toContain("px-0.5");
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — space span for word separation", () => {

  it("renders exactly one pill per token", () => {
    const tokens = [tok(" Hello"), tok("!"), tok(" How")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    expect(getPills(container)).toHaveLength(3);
  });

  it("word-start at idx>0 gets a preceding space span (for copy-paste)", () => {
    const tokens = [tok(" Hello"), tok(" World")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    const stream = getStream(container);
    // All direct inline children (pills + space spans).
    // The space span for 'World' contains " " and does NOT have token-pill class.
    const allSpans = Array.from(stream.querySelectorAll("span:not(.token-pill)"))
      .filter(s => !s.closest(".token-pill")); // exclude dot spans inside pills
    const spaceSpans = allSpans.filter(s => s.textContent === " ");
    expect(spaceSpans.length).toBeGreaterThanOrEqual(1);
  });

  it("first token (idx=0) has no preceding space span", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    const stream = getStream(container);
    const nonPillSpans = Array.from(stream.querySelectorAll("span:not(.token-pill)"))
      .filter(s => !s.closest(".token-pill") && s.textContent === " ");
    // No space before idx=0
    expect(nonPillSpans).toHaveLength(0);
  });

  it("continuation tokens have no space span before them", () => {
    // 'п','р','о' are all continuation — no space spans expected
    const tokens = [tok("п"), tok("р"), tok("о")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    const stream = getStream(container);
    const spaceSpans = Array.from(stream.querySelectorAll("span:not(.token-pill)"))
      .filter(s => !s.closest(".token-pill") && s.textContent === " ");
    expect(spaceSpans).toHaveLength(0);
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — copy-paste token.text concatenation", () => {

  it("joining token.text values preserves word spacing: ' Hello' + '!' + ' How'", () => {
    const tokens = [tok(" Hello"), tok("!"), tok(" How")];
    const joined = tokens.map(t => t.text).join("");
    expect(joined).toBe(" Hello! How");
  });

  it("Cyrillic chars joined without spaces: 'п'+'р'+'о' = 'про'", () => {
    const tokens = [tok("п"), tok("р"), tok("о")];
    const joined = tokens.map(t => t.text).join("");
    expect(joined).toBe("про");
  });

});
