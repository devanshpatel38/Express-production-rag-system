/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Set in layout.tsx via next/font.
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        ink: "#0f0e0c",
        paper: "#f7f3ec",
        accent: "#b45309", // burnt orange - reads as "Express" without using their literal logo color
        muted: "#6b6357",
        rule: "#d8d1c4",
      },
      animation: {
        "fade-up": "fadeUp 0.5s ease-out both",
        "blink": "blink 1.1s steps(2, end) infinite",
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
      },
    },
  },
  plugins: [],
};
