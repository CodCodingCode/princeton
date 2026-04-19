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

    // Re-attach every time the status transitions to "live" — covers the case
    // where we navigate back to the page while a session is in mid-reconnect
    // (status "connecting" → "live") and the first attach call happened before
    // the stream was ready.
    useEffect(() => {
      if (status === "live" && videoRef.current) {
        attachVideo(videoRef.current);
      }
    }, [status]);

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
        className={`relative w-full h-full bg-black overflow-hidden transition-all duration-300 ${
          status === "live" && speaking
            ? "ring-1 ring-brand-500/40 shadow-lg shadow-brand-500/20"
            : ""
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
                {status === "connecting" ? "Connecting" : "Your concierge"}
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
            className="absolute top-14 left-4 text-[11px] font-medium tracking-[0.1em] uppercase text-white/80 hover:text-white bg-black/55 backdrop-blur rounded-full px-3 py-1 ring-1 ring-white/15 shadow-lg shadow-black/30 transition"
          >
            End session
          </button>
        )}

        {status === "live" && caption && (
          // Caption pill. In compact (cockpit) mode, the sidebar occupies the
          // right ~36vw of the viewport, so the caption has to center inside
          // the avatar pane rather than the full viewport. We use a bounded
          // flex row that ends before the sidebar begins and let `justify-
          // center` center the pill inside that zone. In non-compact phases
          // the zone spans the full viewport, so the pill sits in the middle
          // the way it always has.
          <div
            className={`pointer-events-none absolute bottom-6 flex justify-center px-6 ${
              compact ? "left-0 right-[calc(36vw+3rem)]" : "left-0 right-0"
            }`}
          >
            <div className="max-w-[min(80%,680px)] bg-black/65 backdrop-blur-md text-white rounded-xl px-4 py-2 text-sm md:text-base leading-snug text-center ring-1 ring-white/15 shadow-lg shadow-black/30">
              {caption}
            </div>
          </div>
        )}

        {children}
      </div>
    );
  },
);
