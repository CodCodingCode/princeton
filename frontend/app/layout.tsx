import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NeoVax — melanoma oncologist copilot",
  description:
    "Upload a pathology PDF and get a walked NCCN treatment railway, alternative branches, matched clinical trials, and a downloadable oncologist report.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans antialiased bg-ink-950 text-ink-100">
        <header className="border-b border-ink-800 bg-ink-900/60 backdrop-blur sticky top-0 z-30">
          <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
            <a href="/" className="flex items-baseline gap-2">
              <span className="text-teal-400 font-semibold text-lg tracking-tight">
                NeoVax
              </span>
              <span className="text-ink-400 text-xs uppercase tracking-widest">
                melanoma copilot
              </span>
            </a>
            <nav className="text-sm text-ink-400">
              <a href="/upload" className="hover:text-teal-400">
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
