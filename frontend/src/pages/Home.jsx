import { Link } from "react-router-dom";

const MECHANISMS = [
  { id: "E1", label: "Token Provenance",     desc: "Every word traced to its source" },
  { id: "E2", label: "Identity Routing",     desc: "Who you are determines what you see" },
  { id: "E3", label: "Trust Attention",      desc: "Quality sources get more weight" },
  { id: "E4", label: "Live Manifest",        desc: "Machine-readable audit trail" },
  { id: "E5", label: "Hash-Chain Registry",  desc: "Immutable cryptographic ledger" },
  { id: "E6", label: "Fallback Auth",        desc: "Safe defaults for unknown agents" },
];

export default function Home() {
  return (
    <div className="min-h-screen" style={{ background: "#0C1824", color: "#E0E8F0" }}>

      {/* ── Hero ──────────────────────────────────────────────── */}
      <section className="flex flex-col items-center justify-center pt-28 pb-20 px-4 text-center">

        {/* Official logo */}
        <div className="mb-8">
          <img
            src="/logo-dark.png"
            alt="Babylon∞n.ai"
            className="h-16 w-auto mx-auto"
          />
        </div>

        {/* Tagline — per brandbook: italic serif, muted-blue */}
        <p className="tagline text-xl mb-10" style={{ color: "#5A7A9A" }}>
          where every token knows its origin
        </p>

        <p className="text-base max-w-2xl mb-10 leading-relaxed" style={{ color: "#E0E8F0", opacity: 0.8 }}>
          The first LLM provenance attribution system operating{" "}
          <span style={{ color: "#C5963A" }} className="font-semibold">inside</span> the inference
          pipeline. Every token. Every source. Every time.
        </p>

        {/* CTA buttons — Babylonian Gold per brandbook */}
        <div className="flex gap-4 flex-wrap justify-center">
          <Link
            to="/demo"
            className="btn-gold px-7 py-3 rounded-lg text-sm font-semibold"
            style={{ background: "#C5963A", color: "#0C1824" }}
          >
            Try the Demo
          </Link>
          <Link
            to="/pilot"
            className="btn-outline-gold px-7 py-3 rounded-lg text-sm font-semibold"
            style={{ border: "1.5px solid #C5963A", color: "#C5963A" }}
          >
            Pilot Program
          </Link>
        </div>

        <p className="mt-8 text-xs font-mono" style={{ color: "#1B3A5C" }}>
          Patent PCT/IB2026/053131 · 150+ countries · 28 claims
        </p>
      </section>

      {/* ── Problem → Solution ────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-4 py-16 grid md:grid-cols-2 gap-12">
        <div className="rounded-2xl p-8" style={{ background: "rgba(204,0,0,0.06)", border: "1px solid rgba(204,0,0,0.2)" }}>
          <h2 className="text-2xl font-serif mb-4" style={{ color: "#CC0000" }}>The Problem</h2>
          <p className="leading-relaxed text-sm" style={{ color: "#E0E8F0", opacity: 0.8 }}>
            Today's LLMs are black boxes. When they generate text, there's no way to know
            which sources influenced the output, whether those sources are licensed,
            who authorized the query, or whether the result can be trusted.
          </p>
          <p className="leading-relaxed text-sm mt-4" style={{ color: "#E0E8F0", opacity: 0.8 }}>
            All existing solutions (Guardrails AI, Lakera, Arthur AI) are{" "}
            <span style={{ color: "#CC0000" }}>external filters</span> — they sit outside the
            model and see only inputs and outputs, never what happens inside.
          </p>
        </div>
        <div className="rounded-2xl p-8" style={{ background: "rgba(46,125,50,0.06)", border: "1px solid rgba(46,125,50,0.2)" }}>
          <h2 className="text-2xl font-serif mb-4" style={{ color: "#2E7D32" }}>The Solution</h2>
          <p className="leading-relaxed text-sm" style={{ color: "#E0E8F0", opacity: 0.8 }}>
            babyloon.ai operates <span style={{ color: "#2E7D32" }} className="font-semibold">inside</span> the
            inference pipeline. Six patented mechanisms work simultaneously during generation:
            provenance attribution, identity conditioning, trust weighting, live manifests,
            hash-chain registry, and safe fallbacks.
          </p>
          <p className="leading-relaxed text-sm mt-4" style={{ color: "#E0E8F0", opacity: 0.8 }}>
            Every word in an AI response is cryptographically traced to its source,
            without retraining the model.
          </p>
        </div>
      </section>

      {/* ── Six Mechanisms ────────────────────────────────────── */}
      <section className="max-w-4xl mx-auto px-4 py-16">
        <h2 className="text-3xl font-serif text-center mb-3" style={{ color: "#E0E8F0" }}>
          Six Mechanisms. One System.
        </h2>
        <p className="text-center text-sm mb-12 tagline" style={{ color: "#5A7A9A" }}>
          Six terraces of the ziggurat. Six patent claims. One inference pipeline.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {MECHANISMS.map((m, i) => (
            <div
              key={m.id}
              className="rounded-xl p-5 transition-all hover:-translate-y-0.5"
              style={{
                background: "rgba(27, 58, 92, 0.15)",
                border: "1px solid rgba(27, 58, 92, 0.4)",
              }}
              onMouseEnter={(e) => e.currentTarget.style.borderColor = "#C5963A"}
              onMouseLeave={(e) => e.currentTarget.style.borderColor = "rgba(27, 58, 92, 0.4)"}
            >
              <div className="text-xs font-mono mb-1" style={{ color: "#C5963A" }}>{m.id}</div>
              <div className="font-semibold text-sm mb-1 font-sans" style={{ color: "#E0E8F0" }}>{m.label}</div>
              <div className="text-xs" style={{ color: "#5A7A9A" }}>{m.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Legend ────────────────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-4 py-12">
        <div className="rounded-2xl p-8 text-center" style={{ background: "rgba(197,150,58,0.06)", border: "1px solid rgba(197,150,58,0.25)" }}>
          <p className="text-sm leading-relaxed italic font-serif mb-4" style={{ color: "#5A7A9A" }}>
            « І була вся земля однієї мови і одних слів. І сказали вони: побудуймо собі місто та вежу, висотою до неба.
            І змішав Господь мову всієї землі, і звідти розсіяв їх по всій поверхні землі. »
          </p>
          <p className="text-xs font-mono" style={{ color: "#1B3A5C" }}>— Буття 11:1–9</p>
          <p className="text-xs mt-4" style={{ color: "#5A7A9A", opacity: 0.7 }}>
            Five thousand years later, babyloon.ai returns provenance to language. Token by token. Source by source. Infinitely.
          </p>
        </div>
      </section>

      {/* ── Patent ────────────────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-4 py-12 text-center">
        <div className="rounded-2xl p-8" style={{ background: "rgba(27,58,92,0.15)", border: "1px solid rgba(27,58,92,0.4)" }}>
          <div className="text-xs font-mono mb-2" style={{ color: "#C5963A" }}>PCT/IB2026/053131</div>
          <h3 className="text-xl font-serif mb-3" style={{ color: "#E0E8F0" }}>International Patent Protection</h3>
          <p className="text-sm" style={{ color: "#5A7A9A" }}>
            Filed via EPO (ISA) · 150+ countries · 28 claims covering all six mechanisms ·
            Priority date April 2026
          </p>
        </div>
      </section>

      {/* ── Footer ────────────────────────────────────────────── */}
      <footer className="border-t py-12 text-center" style={{ borderColor: "rgba(27,58,92,0.3)" }}>
        {/* Babylooooooon.ai playful element — per brandbook */}
        <div className="mb-6">
          <img
            src="/babyloooooon.png"
            alt="Babylooooooon.ai"
            className="h-8 w-auto mx-auto opacity-60"
          />
        </div>
        <p className="tagline text-sm mb-2" style={{ color: "#5A7A9A" }}>
          where every token knows its origin
        </p>
        <p className="text-xs font-mono" style={{ color: "#1B3A5C" }}>
          babyloon.ai · PCT/IB2026/053131 · April 2026 · CONFIDENTIAL
        </p>
      </footer>
    </div>
  );
}
