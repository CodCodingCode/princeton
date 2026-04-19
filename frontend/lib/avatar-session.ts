// Module-level LiveAvatar session singleton that survives React Fast Refresh
// AND survives the three things that used to drop the session unexpectedly:
//
//   1. Idle timeout: LiveAvatar closes "quiet" sessions after a few minutes.
//      Fix: tick `session.keepAlive()` every 30s while live.
//   2. Token TTL: the mint token has a fixed lifetime; even an active session
//      can be killed when it expires. Fix: on any non-CLIENT_INITIATED
//      disconnect, mint a new token and reconnect transparently.
//   3. Network blips / server-side teardown: same as #2, the reconnect path
//      handles them.
//
// During a transparent reconnect the previous video frame stays on screen
// (we never null `srcObject` for non-CLIENT_INITIATED disconnects) so the
// user doesn't see the "Your concierge" placeholder flash.
//
// The component (AvatarStage) is a thin subscriber: it registers UI-state
// callbacks, attaches its <video> element, and unsubscribes on cleanup. It
// never starts or stops the session on mount/unmount: only an explicit
// user action (clicking "End session") tears down for real.

import {
  LiveAvatarSession,
  SessionEvent,
  SessionDisconnectReason,
  AgentEventsEnum,
} from "@heygen/liveavatar-web-sdk";

export type AvatarStatus = "idle" | "connecting" | "live" | "error";

export interface AvatarSubscriber {
  onStatus?: (s: AvatarStatus) => void;
  onSpeaking?: (speaking: boolean) => void;
  onCaption?: (caption: string) => void;
  onError?: (error: string | null) => void;
}

interface AvatarGlobal {
  session: LiveAvatarSession | null;
  status: AvatarStatus;
  speaking: boolean;
  caption: string;
  error: string | null;
  listeners: Set<AvatarSubscriber>;
  videoEl: HTMLVideoElement | null;
  starting: boolean;
  // Keepalive timer ID: kept on the global so module reload doesn't leak
  // duplicate timers.
  keepaliveId: ReturnType<typeof setInterval> | null;
  // Reconnect bookkeeping. We back off on rapid failure loops.
  reconnectAttempts: number;
  reconnectTimerId: ReturnType<typeof setTimeout> | null;
}

// Tunables.
const KEEPALIVE_INTERVAL_MS = 30_000;
const RECONNECT_BASE_DELAY_MS = 800;
const RECONNECT_MAX_DELAY_MS = 15_000;
const RECONNECT_MAX_ATTEMPTS = 8;

// Survives module reloads.
const G = globalThis as unknown as { __neovaxAvatar?: AvatarGlobal };
if (!G.__neovaxAvatar) {
  G.__neovaxAvatar = {
    session: null,
    status: "idle",
    speaking: false,
    caption: "",
    error: null,
    listeners: new Set(),
    videoEl: null,
    starting: false,
    keepaliveId: null,
    reconnectAttempts: 0,
    reconnectTimerId: null,
  };
}
const state: AvatarGlobal = G.__neovaxAvatar;

function notify() {
  for (const l of state.listeners) {
    l.onStatus?.(state.status);
    l.onSpeaking?.(state.speaking);
    l.onCaption?.(state.caption);
    l.onError?.(state.error);
  }
}

export function subscribe(l: AvatarSubscriber): () => void {
  state.listeners.add(l);
  l.onStatus?.(state.status);
  l.onSpeaking?.(state.speaking);
  l.onCaption?.(state.caption);
  l.onError?.(state.error);
  return () => {
    state.listeners.delete(l);
  };
}

export function attachVideo(el: HTMLVideoElement | null) {
  state.videoEl = el;
  if (el && state.session && state.status === "live") {
    try {
      state.session.attach(el);
    } catch (e) {
      console.warn("avatar.attach failed", e);
    }
  }
}

function startKeepalive() {
  if (state.keepaliveId) return;
  state.keepaliveId = setInterval(() => {
    state.session?.keepAlive().catch((e) => {
      // The SDK's keepAlive can fail transiently: don't let that crash the
      // singleton. The disconnect handler will catch a fatal failure.
      console.warn("avatar.keepAlive failed", e);
    });
  }, KEEPALIVE_INTERVAL_MS);
}

function stopKeepalive() {
  if (state.keepaliveId) {
    clearInterval(state.keepaliveId);
    state.keepaliveId = null;
  }
}

function cancelPendingReconnect() {
  if (state.reconnectTimerId) {
    clearTimeout(state.reconnectTimerId);
    state.reconnectTimerId = null;
  }
}

function scheduleReconnect() {
  if (state.reconnectAttempts >= RECONNECT_MAX_ATTEMPTS) {
    console.warn(
      `[avatar] giving up after ${RECONNECT_MAX_ATTEMPTS} reconnect attempts`,
    );
    state.status = "error";
    state.error = "Connection lost. Click to retry.";
    if (state.videoEl) state.videoEl.srcObject = null;
    notify();
    return;
  }
  // Exponential backoff: 800ms, 1.6s, 3.2s,  capped at 15s.
  const delay = Math.min(
    RECONNECT_BASE_DELAY_MS * 2 ** state.reconnectAttempts,
    RECONNECT_MAX_DELAY_MS,
  );
  state.reconnectAttempts += 1;
  cancelPendingReconnect();
  state.reconnectTimerId = setTimeout(() => {
    state.reconnectTimerId = null;
    void _start({ silent: true });
  }, delay);
}

async function _start(opts: { silent?: boolean } = {}) {
  if (state.starting) return;
  // Public start() is idempotent; silent reconnect bypasses the status guard.
  if (!opts.silent && state.status !== "idle") return;
  state.starting = true;
  state.error = null;
  if (!opts.silent) {
    state.status = "connecting";
    notify();
  }
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
    state.session = session;

    session.on(SessionEvent.SESSION_STREAM_READY, () => {
      if (state.videoEl) {
        try {
          session.attach(state.videoEl);
        } catch (e) {
          console.warn("avatar.attach failed", e);
        }
      }
      state.status = "live";
      state.reconnectAttempts = 0; // success: reset backoff
      notify();
      startKeepalive();
    });

    session.on(
      SessionEvent.SESSION_DISCONNECTED,
      (reason: SessionDisconnectReason) => {
        stopKeepalive();
        state.session = null;
        state.speaking = false;

        if (reason === SessionDisconnectReason.CLIENT_INITIATED) {
          // User clicked End session: clean teardown, drop the video.
          state.status = "idle";
          state.caption = "";
          state.reconnectAttempts = 0;
          cancelPendingReconnect();
          if (state.videoEl) state.videoEl.srcObject = null;
          notify();
          return;
        }

        // Unexpected disconnect (idle timeout, token TTL, network, server).
        // Keep the last video frame visible: do NOT touch srcObject: and
        // queue a transparent reconnect with backoff.
        console.warn(
          `[avatar] disconnected (${reason}): auto-reconnecting (attempt ${state.reconnectAttempts + 1})`,
        );
        notify();
        scheduleReconnect();
      },
    );
    session.on(AgentEventsEnum.AVATAR_SPEAK_STARTED, () => {
      state.speaking = true;
      notify();
    });
    session.on(AgentEventsEnum.AVATAR_SPEAK_ENDED, () => {
      state.speaking = false;
      notify();
    });

    await session.start();
  } catch (e) {
    if (opts.silent) {
      // Silent reconnect failed: back off and try again.
      console.warn("[avatar] silent reconnect failed", e);
      state.session = null;
      scheduleReconnect();
    } else {
      state.error = e instanceof Error ? e.message : String(e);
      state.status = "error";
      state.session = null;
      notify();
    }
  } finally {
    state.starting = false;
  }
}

export const start = () => _start({ silent: false });

export async function stop() {
  const s = state.session;
  cancelPendingReconnect();
  stopKeepalive();
  state.session = null;
  state.status = "idle";
  state.speaking = false;
  state.caption = "";
  state.reconnectAttempts = 0;
  if (state.videoEl) state.videoEl.srcObject = null;
  notify();
  try {
    await s?.stop();
  } catch {
    /* session may already be gone server-side */
  }
}

export async function speak(text: string) {
  const t = text.trim();
  const s = state.session;
  if (!s || !t) return;
  state.caption = t;
  notify();
  try {
    s.repeat(t);
  } catch (e) {
    console.warn("avatar.repeat failed", e);
  }
}

export function getStatus(): AvatarStatus {
  return state.status;
}
