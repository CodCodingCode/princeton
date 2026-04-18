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
// API key stays on the backend - this component POSTs /api/heygen/token and
// never sees the long-lived key.

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import {
  start as startSession,
  stop as stopSession,
  speak as speakSession,
  subscribe as subscribeSession,
  attachVideo,
  type AvatarStatus,
} from "@/lib/avatar-session";

export type { AvatarStatus };

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

    // Subscribe to the singleton and mirror its state into local React state.
    // Critically: the cleanup does NOT stop the session - it just unsubscribes.
    // That's what lets Fast Refresh / remounts happen without killing WebRTC.
    useEffect(() => {
      const unsubscribe = subscribeSession({
        onStatus: setStatus,
        onSpeaking: setSpeaking,
        onCaption: setCaption,
        onError: setError,
      });
      // Bind whichever <video> element this mount happens to own. If a session
      // is already live (Fast Refresh mid-call), this re-attaches the stream.
      attachVideo(videoRef.current);
      return () => {
        unsubscribe();
        // Deliberately DO NOT call stop() here.
      };
    }, []);

    useImperativeHandle(
      ref,
      () => ({
        start: startSession,
        stop: stopSession,
        speak: speakSession,
      }),
      [],
    );

    return (
      <div
        className={`relative w-full h-full bg-black overflow-hidden rounded-2xl border transition-all duration-300 ${
          status === "live" && speaking
            ? "border-brand-500/50 shadow-lg shadow-brand-500/20"
            : "border-neutral-200 shadow-sm"
        }`}
      >
        <video
          ref={videoRef}
          autoPlay
          playsInline
          className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-700 ${
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

        {status === "live" && (
          <button
            onClick={stopSession}
            className="absolute top-32 left-4 text-[11px] font-medium tracking-[0.1em] uppercase text-white/80 hover:text-white bg-black/55 backdrop-blur rounded-full px-3 py-1 ring-1 ring-white/15 shadow-lg shadow-black/30 transition"
          >
            End session
          </button>
        )}

        {status === "live" && caption && (
          <div className="pointer-events-none absolute bottom-10 left-1/2 -translate-x-1/2 max-w-[min(90vw,1100px)] bg-black/65 backdrop-blur-md text-white rounded-2xl px-8 py-5 text-xl md:text-2xl leading-relaxed text-center ring-1 ring-white/15 shadow-2xl shadow-black/40">
            {caption}
          </div>
        )}

        {children}
      </div>
    );
  },
);
