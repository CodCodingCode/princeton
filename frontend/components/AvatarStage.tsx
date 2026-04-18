"use client";

// Full-viewport LiveAvatar base layer. The avatar is the canvas; overlays
// render as `children` on top. Parent drives the session + speech via the
// imperative ref:
//
//   const stage = useRef<AvatarStageHandle>(null);
//   await stage.current?.start();
//   await stage.current?.speak("Hi there.");
//   await stage.current?.stop();
//
// API key stays on the backend — this component POSTs /api/heygen/token and
// never sees the long-lived key.

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import {
  LiveAvatarSession,
  SessionEvent,
  AgentEventsEnum,
} from "@heygen/liveavatar-web-sdk";

export type AvatarStatus = "idle" | "connecting" | "live" | "error";

export interface AvatarStageHandle {
  start: () => Promise<void>;
  stop: () => Promise<void>;
  speak: (text: string) => Promise<void>;
}

interface Props {
  onStatusChange?: (s: AvatarStatus) => void;
  onSpeakingChange?: (speaking: boolean) => void;
  compact?: boolean;
  children?: React.ReactNode;
}

export const AvatarStage = forwardRef<AvatarStageHandle, Props>(
  function AvatarStage(
    { onStatusChange, onSpeakingChange, compact, children },
    ref,
  ) {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const sessionRef = useRef<LiveAvatarSession | null>(null);

    const [status, setStatus] = useState<AvatarStatus>("idle");
    const [speaking, setSpeaking] = useState(false);
    const [caption, setCaption] = useState<string>("");
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
      onStatusChange?.(status);
    }, [status, onStatusChange]);
    useEffect(() => {
      onSpeakingChange?.(speaking);
    }, [speaking, onSpeakingChange]);

    useEffect(() => {
      return () => {
        sessionRef.current?.stop().catch(() => {});
        sessionRef.current = null;
      };
    }, []);

    const start = async () => {
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
        sessionRef.current = session;

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
        session.on(AgentEventsEnum.AVATAR_SPEAK_STARTED, () =>
          setSpeaking(true),
        );
        session.on(AgentEventsEnum.AVATAR_SPEAK_ENDED, () =>
          setSpeaking(false),
        );

        await session.start();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setStatus("error");
        sessionRef.current = null;
      }
    };

    const stop = async () => {
      try {
        await sessionRef.current?.stop();
      } catch {
        /* ignore */
      }
      sessionRef.current = null;
      setStatus("idle");
      setSpeaking(false);
      setCaption("");
    };

    const speak = async (text: string) => {
      const t = text.trim();
      const session = sessionRef.current;
      if (!session || !t) return;
      setCaption(t);
      try {
        session.repeat(t);
      } catch (e) {
        console.warn("avatar.repeat failed", e);
      }
    };

    useImperativeHandle(ref, () => ({ start, stop, speak }), []);

    const statusLabel =
      status === "live"
        ? speaking
          ? "SPEAKING"
          : "LIVE"
        : status.toUpperCase();

    return (
      <div className="relative w-full h-full bg-black overflow-hidden">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-700 ${
            status === "live" ? "opacity-100" : "opacity-0"
          }`}
        />

        {status !== "live" && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center text-neutral-400">
              <div className="w-28 h-28 mx-auto mb-5 rounded-full bg-neutral-900 border border-neutral-800 flex items-center justify-center">
                <svg
                  viewBox="0 0 24 24"
                  className="w-14 h-14 text-neutral-600"
                  fill="currentColor"
                >
                  <path d="M12 12c2.7 0 5-2.3 5-5s-2.3-5-5-5-5 2.3-5 5 2.3 5 5 5zm0 2c-3.3 0-10 1.7-10 5v3h20v-3c0-3.3-6.7-5-10-5z" />
                </svg>
              </div>
              <div className="text-sm font-medium text-neutral-300">
                {status === "connecting" ? "Connecting…" : "Your concierge"}
              </div>
              {status === "error" && error && (
                <div className="text-xs text-red-400 mt-2 max-w-sm mx-auto px-4">
                  {error}
                </div>
              )}
            </div>
          </div>
        )}

        <div
          className={`absolute top-4 left-4 flex items-center gap-2 bg-black/55 backdrop-blur text-white rounded-full px-2.5 py-1 ${
            compact ? "text-[10px]" : "text-[11px]"
          }`}
        >
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
          {statusLabel}
        </div>

        {status === "live" && (
          <button
            onClick={stop}
            className="absolute top-4 right-4 text-[11px] text-white/80 hover:text-white bg-black/55 backdrop-blur rounded-full px-3 py-1 transition"
          >
            End session
          </button>
        )}

        {status === "live" && caption && (
          <div className="pointer-events-none absolute bottom-6 left-1/2 -translate-x-1/2 max-w-[min(80vw,720px)] bg-black/60 backdrop-blur text-white rounded-lg px-4 py-2 text-sm leading-snug text-center">
            {caption}
          </div>
        )}

        {children}
      </div>
    );
  },
);
