"use client";

// HeyGen streaming-avatar panel.
//
// The avatar is a "puppet" — we do not use HeyGen's built-in LLM. Everything
// the avatar says comes from text we pass in via `speak({ task_type: REPEAT })`.
// For now the input box routes directly to the avatar; once the Kimi chat is
// wired, the flow becomes: user → Kimi → text → avatar.speak(...).
//
// API key stays on the backend. We call POST /api/heygen/token to mint a
// short-lived session token; the SDK does the rest.

import { useEffect, useRef, useState } from "react";
import {
  LiveAvatarSession,
  SessionEvent,
  AgentEventsEnum,
} from "@heygen/liveavatar-web-sdk";

interface Turn {
  role: "user" | "avatar";
  text: string;
  at: number;
}

type Status = "idle" | "connecting" | "live" | "error";

export function AvatarPanel() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const avatarRef = useRef<LiveAvatarSession | null>(null);

  const [status, setStatus] = useState<Status>("idle");
  const [speaking, setSpeaking] = useState(false);
  const [caption, setCaption] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<Turn[]>([]);
  const [input, setInput] = useState("");

  useEffect(() => {
    return () => {
      avatarRef.current?.stop().catch(() => {});
      avatarRef.current = null;
    };
  }, []);

  async function startSession() {
    if (status === "connecting" || status === "live") return;
    setError(null);
    setStatus("connecting");
    try {
      const r = await fetch("/api/heygen/token", { method: "POST" });
      if (!r.ok) {
        const detail = await r.text().catch(() => "");
        throw new Error(
          `token mint failed (${r.status}): ${detail.slice(0, 180)}`,
        );
      }
      const { token } = (await r.json()) as { token: string };

      const session = new LiveAvatarSession(token, { voiceChat: false });
      avatarRef.current = session;

      session.on(SessionEvent.SESSION_STREAM_READY, () => {
        if (videoRef.current) session.attach(videoRef.current);
        setStatus("live");
      });

      session.on(SessionEvent.SESSION_DISCONNECTED, () => {
        setStatus("idle");
        setSpeaking(false);
        setCaption("");
        if (videoRef.current) videoRef.current.srcObject = null;
      });

      session.on(AgentEventsEnum.AVATAR_SPEAK_STARTED, () => setSpeaking(true));
      session.on(AgentEventsEnum.AVATAR_SPEAK_ENDED, () => setSpeaking(false));

      await session.start();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("error");
      avatarRef.current = null;
    }
  }

  async function endSession() {
    try {
      await avatarRef.current?.stop();
    } catch {
      /* ignore */
    }
    avatarRef.current = null;
    setStatus("idle");
    setSpeaking(false);
    setCaption("");
  }

  async function say(text: string) {
    const t = text.trim();
    if (!t) return;
    const session = avatarRef.current;
    if (!session || status !== "live") {
      setError("Start a session first.");
      return;
    }
    setTranscript((prev) => [
      ...prev,
      { role: "user", text: t, at: Date.now() },
    ]);
    setCaption(t);
    try {
      session.repeat(t);
      setTranscript((prev) => [
        ...prev,
        { role: "avatar", text: t, at: Date.now() },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const statusLabel: Record<Status, string> = {
    idle: "Start a session to talk with your virtual oncologist",
    connecting: "Connecting to HeyGen…",
    live: speaking ? "Session live · speaking" : "Session live · listening",
    error: "Error — see below",
  };

  return (
    <section className="flex flex-col bg-neutral-50 border-r border-neutral-200 min-h-0">
      <div className="p-5 border-b border-neutral-200 flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-neutral-500 font-semibold">
            Your oncology concierge
          </div>
          <div className="text-sm text-black mt-0.5">{statusLabel[status]}</div>
        </div>
        <button
          onClick={status === "live" ? endSession : startSession}
          disabled={status === "connecting"}
          className={`px-4 py-2 rounded-full text-xs font-medium transition ${
            status === "live"
              ? "bg-neutral-200 text-neutral-700 hover:bg-neutral-300"
              : "bg-brand-700 text-white hover:bg-brand-900"
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {status === "live"
            ? "End session"
            : status === "connecting"
              ? "Connecting…"
              : "Start session"}
        </button>
      </div>

      <div className="p-5 flex-1 flex flex-col min-h-0 gap-4">
        {/* Video frame */}
        <div className="relative aspect-video rounded-2xl bg-black overflow-hidden shrink-0">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            className={`absolute inset-0 w-full h-full object-cover ${
              status === "live" ? "opacity-100" : "opacity-0"
            } transition-opacity`}
          />

          {/* Placeholder shown when no stream */}
          {status !== "live" && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center text-neutral-400">
                <div className="w-24 h-24 mx-auto mb-4 rounded-full bg-neutral-800 border border-neutral-700 flex items-center justify-center">
                  <svg
                    viewBox="0 0 24 24"
                    className="w-12 h-12 text-neutral-500"
                    fill="currentColor"
                  >
                    <path d="M12 12c2.7 0 5-2.3 5-5s-2.3-5-5-5-5 2.3-5 5 2.3 5 5 5zm0 2c-3.3 0-10 1.7-10 5v3h20v-3c0-3.3-6.7-5-10-5z" />
                  </svg>
                </div>
                <div className="text-sm font-medium text-neutral-300">
                  HeyGen avatar
                </div>
                <div className="text-xs text-neutral-500 mt-1">
                  {status === "connecting" ? "connecting…" : "idle"}
                </div>
              </div>
            </div>
          )}

          {/* Caption strip */}
          {status === "live" && caption && (
            <div className="absolute bottom-3 left-3 right-3 bg-black/60 backdrop-blur text-white text-sm rounded-lg px-3 py-2 leading-snug">
              {caption}
            </div>
          )}

          {/* Status dot */}
          <div className="absolute top-3 left-3 flex items-center gap-2 bg-black/60 backdrop-blur text-white text-[11px] rounded-full px-2.5 py-1">
            <span
              className={`inline-block w-1.5 h-1.5 rounded-full ${
                status === "live"
                  ? speaking
                    ? "bg-brand-500 animate-pulse"
                    : "bg-emerald-400"
                  : status === "connecting"
                    ? "bg-amber-400 animate-pulse"
                    : status === "error"
                      ? "bg-red-500"
                      : "bg-neutral-500"
              }`}
            />
            {status === "live"
              ? speaking
                ? "SPEAKING"
                : "LIVE"
              : status.toUpperCase()}
          </div>
        </div>

        {/* Input row */}
        <form
          className="flex items-center gap-2 shrink-0"
          onSubmit={(e) => {
            e.preventDefault();
            const text = input;
            setInput("");
            say(text);
          }}
        >
          <button
            type="button"
            disabled
            title="Voice input — coming soon"
            className="w-11 h-11 rounded-full border border-neutral-200 bg-white text-neutral-300 flex items-center justify-center cursor-not-allowed"
            aria-label="Voice input (coming soon)"
          >
            <svg viewBox="0 0 24 24" className="w-5 h-5" fill="currentColor">
              <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z" />
            </svg>
          </button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              status === "live"
                ? "Type something for the avatar to say…"
                : "Start a session first"
            }
            disabled={status !== "live"}
            className="flex-1 bg-white border border-neutral-200 rounded-full px-4 py-2.5 text-sm text-black placeholder-neutral-500 focus:outline-none focus:border-black disabled:bg-neutral-100 disabled:text-neutral-400"
          />
          <button
            type="submit"
            disabled={status !== "live" || !input.trim()}
            className="px-5 py-2.5 rounded-full bg-brand-700 hover:bg-brand-900 text-white text-sm font-medium disabled:opacity-30 disabled:cursor-not-allowed transition"
          >
            Say it
          </button>
        </form>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 text-red-700 text-xs p-3 shrink-0">
            {error}
          </div>
        )}

        {/* Transcript */}
        <div className="flex-1 min-h-0 overflow-y-auto rounded-xl border border-neutral-200 bg-white p-4">
          <div className="text-[11px] uppercase tracking-widest text-neutral-500 font-semibold mb-3">
            Transcript
          </div>
          {transcript.length === 0 ? (
            <div className="text-sm text-neutral-500">
              Anything the avatar speaks will show up here. Once Kimi is wired
              in, this becomes the full conversation log.
            </div>
          ) : (
            <div className="space-y-3">
              {transcript.map((turn, i) => (
                <div key={i}>
                  <div className="text-[10px] uppercase tracking-wider text-neutral-400 mb-0.5">
                    {turn.role === "user" ? "You" : "Avatar · spoken"}
                  </div>
                  <div
                    className={`text-sm leading-relaxed ${
                      turn.role === "user" ? "text-neutral-600" : "text-black"
                    }`}
                  >
                    {turn.text}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
