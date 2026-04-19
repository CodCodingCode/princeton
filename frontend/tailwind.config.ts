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
      // Single typeface across the app. `serif` and `mono` intentionally
      // resolve to the same Inter stack so the ~200 existing font-serif /
      // font-mono utilities keep working without audit-and-replace, but
      // every surface now renders in one consistent face. Pair with
      // `tabular-nums` where numeric alignment matters.
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
          "var(--font-sans)",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
        ],
        mono: [
          "var(--font-sans)",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
