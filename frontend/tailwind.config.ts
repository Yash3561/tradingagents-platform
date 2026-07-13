import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── Brand palette ─────────────────────────────────
        bg: {
          base: "#0A0E1A",
          surface: "#0F1629",
          card: "#141D30",
          elevated: "#1A2540",
        },
        border: {
          DEFAULT: "#1E2D45",
          subtle: "#162033",
          bright: "#2D4470",
        },
        accent: {
          DEFAULT: "#2D7DD2",
          bright: "#4A9AEF",
          muted: "#1A4C82",
          glow: "rgba(45,125,210,0.25)",
        },
        gain: {
          DEFAULT: "#00E676",
          muted: "#00A854",
          bg: "rgba(0,230,118,0.08)",
        },
        loss: {
          DEFAULT: "#FF3D57",
          muted: "#C42E44",
          bg: "rgba(255,61,87,0.08)",
        },
        warn: {
          DEFAULT: "#FFB740",
          muted: "#CC9230",
          bg: "rgba(255,183,64,0.08)",
        },
        text: {
          primary: "#E8F0FE",
          secondary: "#8B9DC0",
          muted: "#4D6080",
          inverse: "#0A0E1A",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
        display: ["Space Grotesk", "Inter", "system-ui", "sans-serif"],
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(30,45,69,0.8)",
        "card-hover": "0 4px 16px rgba(0,0,0,0.5), 0 0 0 1px rgba(45,125,210,0.3)",
        "accent-glow": "0 0 20px rgba(45,125,210,0.35)",
        "gain-glow": "0 0 12px rgba(0,230,118,0.3)",
        "loss-glow": "0 0 12px rgba(255,61,87,0.3)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.4s cubic-bezier(0.16,1,0.3,1)",
        "price-flash-up": "priceFlashUp 0.6s ease-out",
        "price-flash-down": "priceFlashDown 0.6s ease-out",
        marquee: "marquee 40s linear infinite",
        "marquee-slow": "marquee 60s linear infinite",
      },
      keyframes: {
        fadeIn: { from: { opacity: "0" }, to: { opacity: "1" } },
        slideUp: { from: { opacity: "0", transform: "translateY(12px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        priceFlashUp: { "0%,100%": { backgroundColor: "transparent" }, "50%": { backgroundColor: "rgba(0,230,118,0.15)" } },
        priceFlashDown: { "0%,100%": { backgroundColor: "transparent" }, "50%": { backgroundColor: "rgba(255,61,87,0.15)" } },
        marquee: { from: { transform: "translateX(0)" }, to: { transform: "translateX(-50%)" } },
      },
      backdropBlur: { xs: "2px" },
    },
  },
  plugins: [],
};

export default config;
