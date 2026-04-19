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
  // The full text of the most recent chunk passed to speak(). The on-screen
  // caption mirrors this directly — each speak() call REPLACES the caption
  // with the new chunk, so a multi-sentence reply cycles sentence-by-
  // sentence instead of growing or word-pacing. No ticker, no accumulation,
  // no race conditions.
  captionFullText: string;
  error: string | null;
  listeners: Set<AvatarSubscriber>;
  videoEl: HTMLVideoElement | null;
  starting: boolean;
  // Cached MediaStream captured from the video element's srcObject after
  // the SDK's first `session.attach(el)` bind. Re-used on every subsequent
  // mount so we can bypass the SDK entirely when re-binding to a fresh
  // <video> on remount. Without this, client-side nav between /  and
  // /patient leaves the new video element with no usable srcObject and
  // the user sees a frozen first frame.
  stream: MediaStream | null;
  // Keepalive timer ID: kept on the global so module reload doesn't leak
  // duplicate timers.
  keepaliveId: ReturnType<typeof setInterval> | null;
  // Reconnect bookkeeping. We back off on rapid failure loops.
  reconnectAttempts: number;
  reconnectTimerId: ReturnType<typeof setTimeout> | null;
  // Narration-dedup set. Each page calls markSpoken(key) after firing a
  // scripted line, and hasSpoken(key) before firing one. Survives
  // unmount/remount so that toggling between / and /patient does NOT
  // re-greet, re-speak the results summary, or replay milestone lines
  // when the SSE stream rebroadcasts past events. Callers typically
  // namespace keys with the caseId so distinct cases narrate fresh.
  spokenKeys: Set<string>;
}

// Tunables.
const KEEPALIVE_INTERVAL_MS = 30_000;
const RECONNECT_BASE_DELAY_MS = 800;
const RECONNECT_MAX_DELAY_MS = 15_000;
const RECONNECT_MAX_ATTEMPTS = 8;

// Survives module reloads.
const G = globalThis as unknown as { __onkosAvatar?: AvatarGlobal };
if (!G.__onkosAvatar) {
  G.__onkosAvatar = {
    session: null,
    status: "idle",
    speaking: false,
    caption: "",
    captionFullText: "",
    error: null,
    listeners: new Set(),
    videoEl: null,
    starting: false,
    stream: null,
    keepaliveId: null,
    reconnectAttempts: 0,
    reconnectTimerId: null,
    spokenKeys: new Set(),
  };
}
const state: AvatarGlobal = G.__onkosAvatar;

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

// Synchronous readers for callers that need to seed initial React state
// with the singleton's current values. Without these, toggling Patient ↔
// Clinician view would start the new AvatarStage at status="idle" for one
// frame, covering the video with the idle poster even though the session
// is already live.

export function getStatus(): AvatarStatus {
  return state.status;
}

export function getSpeaking(): boolean {
  return state.speaking;
}

export function getCaption(): string {
  return state.caption;
}

export function hasLiveSession(): boolean {
  return state.session !== null;
}

// ── Narration-dedup helpers ─────────────────────────────────────────────
// Callers should use a stable key per line+case, e.g.
//   hasSpoken(`results:${caseId}`)  /  markSpoken(`results:${caseId}`)
// clearSpokenKeys() resets the set (wired to stop() + new-case upload).

export function hasSpoken(key: string): boolean {
  return state.spokenKeys.has(key);
}

export function markSpoken(key: string): void {
  state.spokenKeys.add(key);
}

export function clearSpokenKeys(): void {
  state.spokenKeys.clear();
}

export function attachVideo(el: HTMLVideoElement | null) {
  state.videoEl = el;
  if (!el) return;

  // Step 1: ask the SDK to attach. This sets srcObject and hooks up the
  // HeyGen session's internal lifecycle. If the SDK has already attached
  // to a prior (now-unmounted) element it may or may not cleanly re-bind
  // to the new one — so we always follow up with a manual bind using the
  // stream we captured on the first successful attach.
  if (state.session) {
    try {
      state.session.attach(el);
    } catch (e) {
      console.warn("avatar.attach failed", e);
    }
  }

  // Step 2: capture the MediaStream the first time we see one on an
  // element. After this, we own the stream reference and don't have to
  // trust the SDK to rebind it on remount.
  const current = el.srcObject;
  if (!state.stream && current instanceof MediaStream) {
    state.stream = current;
  }

  // Step 3: if srcObject isn't a live MediaStream yet (fresh <video> from
  // a client-side navigation, SDK didn't rebind), force-bind the cached
  // one. This is the core of the fix — the user was seeing a frozen first
  // frame because the new element's srcObject was either null or a stale
  // reference that no longer pumped frames.
  if (state.stream && el.srcObject !== state.stream) {
    try {
      el.srcObject = state.stream;
    } catch (e) {
      console.warn("avatar.srcObject bind failed", e);
    }
  }

  // Step 4: actively play. `autoplay` alone doesn't reliably fire when
  // srcObject is swapped on a mounted element, especially after a route
  // transition. Swallow AbortError and NotAllowedError — the former is
  // harmless (replaced by a newer play()), the latter just means the
  // browser wants one more user gesture, which the user will provide by
  // clicking anywhere on the page.
  void el.play().catch(() => {});
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
        // Capture the MediaStream as soon as the SDK binds it. From this
        // point on, every future mount's <video> gets bound against
        // state.stream directly — we stop relying on the SDK to rebind.
        const maybeStream = state.videoEl.srcObject;
        if (maybeStream instanceof MediaStream) {
          state.stream = maybeStream;
        }
        void state.videoEl.play().catch(() => {});
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
          state.captionFullText = "";
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

    // The on-screen caption is driven EXCLUSIVELY by speak(). We used to
    // also wire up AVATAR_TRANSCRIPTION_CHUNK / AVATAR_TRANSCRIPTION as
    // "defensive passthroughs" in case we ever turned on voiceChat mode —
    // but in our current mode (voiceChat: false, repeat()-driven TTS) the
    // SDK still emits those events at inconsistent cadence, and their
    // handlers overwrote speak()'s caption with stale or cumulative text.
    // That showed up to the user as the caption cycling through three
    // states per reply: section 1, section 2, then both concatenated.
    // No subscription = no fight, one caption per chunk.

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
  state.captionFullText = "";
  state.reconnectAttempts = 0;
  state.stream = null;
  // Reset narration dedup so the next session can greet / re-narrate from
  // scratch. Without this, clicking End session → Begin would keep the
  // avatar silent because the last session's keys would still be in the set.
  state.spokenKeys.clear();
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
  // One chunk in, one caption out. Each speak() call REPLACES the on-screen
  // caption with exactly the text passed in — no streaming, no growing
  // text, no word-reveal ticker. Multi-sentence chat replies fire one
  // speak() per sentence, and the caption cycles through them in sync with
  // the avatar's TTS.
  state.captionFullText = t;
  state.caption = t;
  notify();
  try {
    s.repeat(t);
  } catch (e) {
    console.warn("avatar.repeat failed", e);
  }
}
