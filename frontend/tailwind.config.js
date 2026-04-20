/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Babyloon.ai brand palette (Brandbook v1.0)
        "deep-azure":      "#1B3A5C",  // Primary — text on light bg
        "babylonian-gold": "#C5963A",  // Accent  — ∞ symbol, ziggurat, CTA
        "ink":             "#0C1824",  // Background dark
        "silver":          "#E0E8F0",  // Text on dark bg
        "parchment":       "#FAF8F4",  // Background light
        "muted-blue":      "#5A7A9A",  // Secondary — .ai, tagline, subdued text
        // Trust indicators
        "trust-high":   "#2E7D32",
        "trust-medium": "#F9A825",
        "trust-low":    "#CC0000",
      },
      fontFamily: {
        serif: ["Cormorant Garamond", "Georgia", "Libre Baskerville", "serif"],
        sans:  ["Inter", "Helvetica Neue", "Helvetica", "Arial", "sans-serif"],
        mono:  ["JetBrains Mono", "Fira Code", "monospace"],
      },
      backgroundImage: {
        "gold-gradient": "linear-gradient(135deg, #C5963A 0%, #E8B86D 50%, #C5963A 100%)",
      },
    },
  },
  plugins: [],
};
