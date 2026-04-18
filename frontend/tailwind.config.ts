import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Single accent: deep navy. Used sparingly - only for the primary
        // CTA, active states, and one hero status dot. Everything else leans
        // on neutrals so hierarchy comes from typography + weight, not color.
        brand: {
          50: "#eef2f8",
          100: "#d7dff0",
          500: "#1e3a8a",
          700: "#0b2545",
          900: "#061630",
        },
        // Teal is retained as a key so stray references don't break the
        // build, but every shade points at a neutral - there is no remaining
        // colored saturation from the old palette.
        teal: {
          50: "#fafafa",
          100: "#f4f4f4",
          300: "#737373",
          400: "#262626",
          500: "#171717",
          600: "#0a0a0a",
          700: "#0a0a0a",
        },
        ink: {
          50: "#000000",
          100: "#0a0a0a",
          200: "#141414",
          300: "#333333",
          400: "#6b6b6b",
          500: "#8a8a8a",
          600: "#a3a3a3",
          700: "#d4d4d4",
          800: "#e7e7e7",
          900: "#f4f4f4",
          950: "#ffffff",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-sans)",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
        ],
        serif: [
          "var(--font-serif)",
          "ui-serif",
          "Georgia",
          "Cambria",
          "Times New Roman",
          "serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
