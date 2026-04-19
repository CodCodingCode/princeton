import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";
import { HeaderNav } from "@/components/HeaderNav";

// One typeface across the whole app. Inter ships tabular-nums + opsz ranges
// that cover every register we need (numeric readouts, body copy, display
// headlines). The `--font-serif` and `--font-mono` CSS vars alias the same
// Inter family so existing `font-serif` / `font-mono` classes keep rendering
// without hunting them all down.
const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Onkos - oncologist copilot",
  description:
    "Upload a patient's oncology records and receive a guideline-grounded treatment plan, matched clinical trials, and a downloadable oncologist report.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={sans.variable}>
      <body
        className="min-h-screen font-sans antialiased bg-[#faf7f3] text-black"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='60' height='52' viewBox='0 0 60 52'%3E%3Cpolygon points='30,4 54,16 54,40 30,52 6,40 6,16' fill='none' stroke='%23000' stroke-width='0.7' opacity='0.045'/%3E%3C/svg%3E\")",
          backgroundSize: "60px 52px",
        }}
      >
        <header className="fixed top-0 left-0 right-0 z-30 bg-[#faf7f3]/80 backdrop-blur-xl border-b border-neutral-200/60">
          <div className="px-6 h-16 flex items-center justify-between">
            <a href="/" className="flex flex-col items-start gap-0.5 group">
              <span className="font-serif text-4xl leading-none tracking-tight text-black">
                Onkos
              </span>
              <span className="text-[10px] uppercase tracking-[0.2em] text-neutral-500 font-medium">
                Cursor for Oncologists
              </span>
            </a>
            <Suspense fallback={null}>
              <HeaderNav />
            </Suspense>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
