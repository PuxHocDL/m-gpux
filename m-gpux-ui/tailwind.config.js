/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Editorial emerald: inspired by modern registry/documentation sites.
        brand: {
          50: "#EDF8F3",
          100: "#D8EFE5",
          200: "#B3DDCC",
          300: "#7FC4AC",
          400: "#35A27F",
          500: "#007A5E",
          600: "#00664F",
          700: "#005240",
          800: "#073F34",
          900: "#0B332B",
        },
        // Warm paper surfaces.
        cream: {
          50: "#FBFAF6",
          100: "#F5F4EE",
          200: "#EAE8DE",
        },
        ink: {
          DEFAULT: "#181915",
          soft: "#41443D",
          muted: "#70736B",
          faint: "#9A9D94",
        },
        line: "#DEDDD4",
        signal: {
          lime: "#A8D5C0",
          blue: "#9ECFC3",
          violet: "#C7BFA8",
        },
        term: {
          bg: "#073D2E",
          panel: "#0B4937",
          line: "#246B55",
          text: "#F2F5EF",
          dim: "#8DBBAA",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Lora", "Georgia", "ui-serif", "serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(18,45,36,0.04), 0 12px 30px -18px rgba(18,45,36,0.2)",
        card: "0 1px 0 rgba(255,255,255,0.8) inset, 0 24px 70px -42px rgba(18,45,36,0.32)",
        glow: "0 0 0 1px rgba(0,122,94,0.18), 0 22px 70px -28px rgba(0,122,94,0.42)",
        term: "0 38px 90px -42px rgba(12,42,33,0.64), 0 8px 24px -14px rgba(12,42,33,0.38)",
      },
      backgroundImage: {
        "brand-grad": "linear-gradient(120deg,#168B6E 0%,#007A5E 52%,#35A27F 100%)",
      },
      keyframes: {
        blink: { "0%,49%": { opacity: "1" }, "50%,100%": { opacity: "0" } },
        marquee: { "0%": { transform: "translateX(0)" }, "100%": { transform: "translateX(-50%)" } },
      },
      animation: {
        blink: "blink 1s step-end infinite",
        marquee: "marquee 28s linear infinite",
      },
    },
  },
  plugins: [],
};
