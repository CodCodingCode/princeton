import type { Metadata } from "next";
import { Inter, Instrument_Serif } from "next/font/google";
import "./globals.css";

const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const serif = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "NeoVax - oncologist copilot",
  description:
    "Upload a patient's oncology document folder and get a dynamic treatment railway grounded in phase-2+ trial literature, matched clinical trials, and a downloadable oncologist report.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
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
            <a href="/" className="flex items-baseline gap-3 group">
              <span className="font-serif text-3xl leading-none tracking-tight text-black">
                NeoVax
              </span>
              <span className="hidden sm:inline text-[11px] uppercase tracking-[0.2em] text-neutral-500 font-medium">
                Oncology Copilot
              </span>
            </a>
            <nav className="flex items-center gap-1">
              <a
                href="/upload"
                className="inline-flex items-center gap-1.5 rounded-full bg-black px-4 py-1.5 text-sm font-medium text-white transition hover:bg-brand-700 mr-12"
              >
                New case
                <span aria-hidden className="text-base leading-none">
                  →
                </span>
              </a>
            </nav>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
