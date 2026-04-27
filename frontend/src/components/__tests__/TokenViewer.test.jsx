import { render } from "@testing-library/react";
import { describe, it, expect, beforeAll, vi } from "vitest";
import TokenViewer from "../TokenViewer";

// TokenViewer reads window dimensions for popup positioning.
beforeAll(() => {
  vi.stubGlobal("innerWidth",  1280);
  vi.stubGlobal("innerHeight", 800);
  // Silence the DEV debug console.log that fires during tests.
  vi.spyOn(console, "log").mockImplementation(() => {});
});

/** Minimal token fixture. attribution=[] suppresses the hover popup. */
function tok(text, trust = 0.85) {
  return { text, trust_avg: trust, position: 0, attribution: [] };
}

/** All .token-pill spans — one per token, excludes space / dot spans. */
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
    const fs = getStream(container).style.fontSize;
    // jsdom normalises 0 → "0px"; React may leave it as "0".
    expect(fs === "0" || fs === "0px").toBe(true);
  });

  it("every token pill has fontSize '14px'", () => {
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

  it("stream children are a flat array (flatMap) — no extra wrapper divs", () => {
    const { container } = render(
      <TokenViewer tokens={[tok(" Art"), tok("ificial")]} />,
    );
    // The stream element's direct children should all be <span> elements only.
    const stream = getStream(container);
    const nonSpanChildren = Array.from(stream.children).filter(el => el.tagName !== "SPAN");
    expect(nonSpanChildren).toHaveLength(0);
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — isWordStart detection (charCode-based)", () => {

  it("ASCII space U+0020 → word-start (Mistral after backend decode)", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello"), tok(" World")]} />);
    const pills = getPills(container);
    // Both are word-start → space span exists before 'World' pill
    const stream = getStream(container);
    const spaceSpans = Array.from(stream.children).filter(
      s => !s.classList.contains("token-pill") && s.textContent === " ",
    );
    expect(spaceSpans.length).toBeGreaterThanOrEqual(1);
  });

  it("▁ prefix U+2581 → word-start (raw SentencePiece)", () => {
    const { container } = render(<TokenViewer tokens={[tok("▁Hello")]} />);
    const [pill] = getPills(container);
    // ▁ stripped → pill shows "Hello"
    expect(pill.textContent).toBe("Hello");
  });

  it("Ġ prefix U+0120 → word-start (GPT-2 BPE)", () => {
    const { container } = render(<TokenViewer tokens={[tok("ĠHello")]} />);
    const [pill] = getPills(container);
    // Ġ stripped → pill shows "Hello"
    expect(pill.textContent).toBe("Hello");
  });

  it("plain 'parency' (no prefix) → continuation, no space before it", () => {
    const tokens = [tok(" trans"), tok("parency")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    const stream = getStream(container);
    // Only one space span expected (before 'trans', idx=0 has no spacer)
    const spaceSpans = Array.from(stream.children).filter(
      s => !s.classList.contains("token-pill") && s.textContent === " ",
    );
    // idx=0 ' trans' → no spacer (first token); 'parency' → no spacer (continuation)
    expect(spaceSpans).toHaveLength(0);
  });

  it("plain Cyrillic 'р' → continuation, no space before it", () => {
    const tokens = [tok("п"), tok("р"), tok("о")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    const stream = getStream(container);
    const spaceSpans = Array.from(stream.children).filter(
      s => !s.classList.contains("token-pill") && s.textContent === " ",
    );
    expect(spaceSpans).toHaveLength(0);
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — pill content and count", () => {

  it("renders exactly one pill per token", () => {
    const tokens = [tok(" Hello"), tok("!"), tok(" How")];
    const { container } = render(<TokenViewer tokens={tokens} />);
    expect(getPills(container)).toHaveLength(3);
  });

  it("word-start ' Hello' → pill shows 'Hello' (leading space stripped)", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    expect(getPills(container)[0].textContent).toBe("Hello");
  });

  it("continuation 'ness' → pill shows 'ness'", () => {
    const { container } = render(<TokenViewer tokens={[tok("ness")]} />);
    const [pill] = getPills(container);
    expect(pill.textContent).toBe("ness");
    expect(pill.textContent.startsWith(" ")).toBe(false);
  });

  it("Cyrillic continuation 'р' → pill shows 'р' (no leading space)", () => {
    const { container } = render(<TokenViewer tokens={[tok("р")]} />);
    expect(getPills(container)[0].textContent).toBe("р");
  });

  it("empty token → pill shows zero-width space (keeps pill visible)", () => {
    const { container } = render(<TokenViewer tokens={[tok("")]} />);
    expect(getPills(container)[0].textContent).toBe("​"); // U+200B
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — horizontal padding rules", () => {

  it("word-start pill has px-0.5 (horizontal breathing room)", () => {
    const { container } = render(<TokenViewer tokens={[tok(" Hello")]} />);
    expect(getPills(container)[0].className).toContain("px-0.5");
  });

  it("continuation pill does NOT have px-0.5 (flush rendering)", () => {
    const { container } = render(<TokenViewer tokens={[tok("parency")]} />);
    expect(getPills(container)[0].className).not.toContain("px-0.5");
  });

  it("Cyrillic continuation 'р' has no px-0.5", () => {
    const { container } = render(<TokenViewer tokens={[tok("р")]} />);
    expect(getPills(container)[0].className).not.toContain("px-0.5");
  });

});

// ─────────────────────────────────────────────────────────────────────────────

describe("TokenViewer — copy-paste token.text concatenation", () => {

  it("joining ' Hello' + '!' + ' How' gives ' Hello! How'", () => {
    const tokens = [tok(" Hello"), tok("!"), tok(" How")];
    expect(tokens.map(t => t.text).join("")).toBe(" Hello! How");
  });

  it("Cyrillic 'п'+'р'+'о' joined = 'про' (no spaces)", () => {
    const tokens = [tok("п"), tok("р"), tok("о")];
    expect(tokens.map(t => t.text).join("")).toBe("про");
  });

});
