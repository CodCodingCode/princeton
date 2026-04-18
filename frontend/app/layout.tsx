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
  title: "NeoVax — oncologist copilot",
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
      <body className="min-h-screen font-sans antialiased bg-white text-black">
        <header className="fixed top-0 left-0 right-0 z-30 bg-white/25 backdrop-blur-md border-b border-white/20">
          <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
            <a href="/" className="flex items-baseline gap-3">
              <span className="text-black/80 font-semibold text-lg tracking-tight drop-shadow-sm">
                NeoVax
              </span>
              <span className="text-neutral-700/80 text-xs uppercase tracking-widest hidden sm:inline">
                oncology copilot
              </span>
            </a>
            <nav className="text-sm text-neutral-700/80">
              <a href="/upload" className="hover:text-black transition">
                New case
              </a>
            </nav>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
