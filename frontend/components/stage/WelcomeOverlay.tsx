"use client";

interface Props {
  onBegin: () => void;
  busy?: boolean;
}

export function WelcomeOverlay({ onBegin, busy }: Props) {
  return (
    <div className="absolute inset-0 flex items-center justify-center p-6 pointer-events-none">
      <div className="pointer-events-auto max-w-lg w-full rounded-2xl bg-white/95 backdrop-blur shadow-2xl p-8 text-center">
        <div className="eyebrow mb-3">NeoVax</div>
        <h1 className="font-serif text-3xl md:text-4xl text-black leading-tight mb-3">
          Your virtual oncology concierge
        </h1>
        <p className="text-sm text-neutral-600 leading-relaxed mb-6">
          Share your records and I&apos;ll walk you through what the guidelines
          say, trial by trial, in plain English. When you&apos;re ready, press
          begin - I&apos;ll greet you and we can get started.
        </p>
        <button
          type="button"
          onClick={onBegin}
          disabled={busy}
          className="px-8 py-3 rounded-full bg-brand-700 hover:bg-brand-900 text-white text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {busy ? "Connecting…" : "Begin"}
        </button>
      </div>
    </div>
  );
}
