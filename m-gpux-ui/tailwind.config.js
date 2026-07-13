/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm pastel-orange brand scale
        brand: {
          50: "#FFF7ED",
          100: "#FFEDD5",
          200: "#FED7AA",
          300: "#FDBA74",
          400: "#FB923C",
          500: "#F97316",
          600: "#EA580C",
          700: "#C2410C",
          800: "#9A3412",
          900: "#7C2D12",
        },
        // Cream / warm-white surfaces
        cream: {
          50: "#FFFCF8",
          100: "#FFF8F1",
          200: "#FFF1E6",
        },
        // Warm ink text
        ink: {
          DEFAULT: "#1C1917",
          soft: "#44403C",
          muted: "#78716C",
          faint: "#A8A29E",
        },
        line: "#F6E6D6",
        // Terminal palette (warm charcoal)
        term: {
          bg: "#1B1714",
          panel: "#221C18",
          line: "#33291F",
          text: "#E7E0D6",
          dim: "#9C9286",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Sora", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(124,45,18,0.04), 0 8px 24px -12px rgba(234,88,12,0.18)",
        card: "0 1px 0 rgba(255,255,255,0.6) inset, 0 10px 40px -16px rgba(234,88,12,0.25)",
        glow: "0 0 0 1px rgba(251,146,60,0.25), 0 18px 60px -20px rgba(249,115,22,0.45)",
        term: "0 30px 80px -30px rgba(124,45,18,0.45), 0 8px 24px -12px rgba(0,0,0,0.25)",
      },
      backgroundImage: {
        "brand-grad": "linear-gradient(120deg,#FB923C 0%,#F97316 45%,#FDBA74 100%)",
        "brand-soft": "linear-gradient(160deg,#FFF7ED 0%,#FFFFFF 60%)",
      },
      keyframes: {
        aurora: {
          "0%,100%": { transform: "translate3d(0,0,0) scale(1)", opacity: "0.55" },
          "50%": { transform: "translate3d(4%,-3%,0) scale(1.15)", opacity: "0.8" },
        },
        floaty: {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
        "gradient-x": {
          "0%,100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        blink: { "0%,49%": { opacity: "1" }, "50%,100%": { opacity: "0" } },
        marquee: { "0%": { transform: "translateX(0)" }, "100%": { transform: "translateX(-50%)" } },
        pop: { "0%": { transform: "scale(0.8)", opacity: "0" }, "100%": { transform: "scale(1)", opacity: "1" } },
      },
      animation: {
        aurora: "aurora 14s ease-in-out infinite",
        floaty: "floaty 6s ease-in-out infinite",
        shimmer: "shimmer 2.4s linear infinite",
        "gradient-x": "gradient-x 6s ease infinite",
        blink: "blink 1s step-end infinite",
        marquee: "marquee 28s linear infinite",
        pop: "pop 0.25s ease-out",
      },
    },
  },
  plugins: [],
};
