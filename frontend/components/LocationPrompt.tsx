"use client";

// Auto-fetching location banner for the Trials tab.
//
// On mount: restore any previously-granted location from localStorage. If we
// don't have one, fire navigator.geolocation.getCurrentPosition() immediately
// (this triggers the browser's native permission dialog on first use, and is
// instant on subsequent visits since the browser caches the grant). No text
// input, no "use my location" button - the user either grants the permission
// once or the distance UI quietly stays off.
//
// We still expose a "Change" button so a user who gave the wrong city can
// re-trigger a lookup, and a "Clear" path to wipe the stored location.

import { useEffect, useState } from "react";
import type { UserLocation } from "@/lib/geo";

interface Props {
  caseId: string;
  location: UserLocation | null;
  onChange: (loc: UserLocation | null) => void;
}

export function locationStorageKey(caseId: string): string {
  return `onkos:location:${caseId}`;
}

export function readStoredLocation(caseId: string): UserLocation | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(locationStorageKey(caseId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as UserLocation;
    if (typeof parsed.lat === "number" && typeof parsed.lng === "number") {
      return parsed;
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function writeStoredLocation(
  caseId: string,
  loc: UserLocation | null,
): void {
  if (typeof window === "undefined") return;
  try {
    if (loc == null) {
      window.localStorage.removeItem(locationStorageKey(caseId));
    } else {
      window.localStorage.setItem(
        locationStorageKey(caseId),
        JSON.stringify(loc),
      );
    }
  } catch {
    /* ignore */
  }
}

type Status =
  | "idle"
  | "locating"
  | "ready"
  | "denied"
  | "unsupported"
  | "error";

function requestBrowserLocation(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      reject(new Error("Geolocation is not supported by this browser."));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      maximumAge: 5 * 60 * 1000,
      timeout: 8000,
    });
  });
}

export function LocationPrompt({ caseId, location, onChange }: Props) {
  const [status, setStatus] = useState<Status>(location ? "ready" : "idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const captureLocation = async () => {
    setStatus("locating");
    setErrorMsg(null);
    try {
      const pos = await requestBrowserLocation();
      const loc: UserLocation = {
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        source: "browser",
      };
      writeStoredLocation(caseId, loc);
      onChange(loc);
      setStatus("ready");
    } catch (e) {
      if (e instanceof GeolocationPositionError) {
        if (e.code === 1) {
          // PERMISSION_DENIED
          setStatus("denied");
          setErrorMsg(
            "Location permission denied. Trials will still show, ranked by eligibility.",
          );
          return;
        }
        if (e.code === 2) {
          // POSITION_UNAVAILABLE
          setStatus("error");
          setErrorMsg("Couldn't determine your location right now.");
          return;
        }
        if (e.code === 3) {
          // TIMEOUT
          setStatus("error");
          setErrorMsg("Location lookup timed out.");
          return;
        }
      }
      if (e instanceof Error && /not supported/i.test(e.message)) {
        setStatus("unsupported");
        setErrorMsg(null);
        return;
      }
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : String(e));
    }
  };

  // Auto-fire once on mount when we don't already have a cached location.
  useEffect(() => {
    if (location) {
      setStatus("ready");
      return;
    }
    captureLocation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const clear = () => {
    writeStoredLocation(caseId, null);
    onChange(null);
    setStatus("idle");
    setErrorMsg(null);
  };

  // ── Render states ────────────────────────────────────────────────────────

  if (status === "locating") {
    return (
      <div className="card p-3 flex items-center gap-2 text-xs text-neutral-600">
        <span className="inline-block w-2 h-2 rounded-full bg-brand-700 animate-pulse" />
        <span>Locating you to rank trials by nearest site</span>
      </div>
    );
  }

  if (status === "ready" && location) {
    return (
      <div className="card p-3 flex items-center justify-between gap-3">
        <div className="min-w-0 flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
          <div className="min-w-0">
            <div className="text-xs text-neutral-500 leading-tight">
              Trials sorted by distance from
            </div>
            <div className="text-sm text-black ">
              {location.label ||
                `${location.lat.toFixed(3)}, ${location.lng.toFixed(3)}`}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={captureLocation}
          className="text-[11px] text-neutral-500 hover:text-black transition shrink-0"
        >
          Refresh
        </button>
      </div>
    );
  }

  if (status === "denied" || status === "error" || status === "unsupported") {
    return (
      <div className="card p-3 flex items-center justify-between gap-3 text-xs">
        <span className="text-neutral-600">
          {errorMsg ||
            "Location isn't available; trials are sorted by eligibility only."}
        </span>
        <button
          type="button"
          onClick={captureLocation}
          className="text-[11px] text-brand-700 hover:text-black transition shrink-0"
        >
          Retry
        </button>
      </div>
    );
  }

  // idle: shouldn't linger, but render a minimal row just in case
  return (
    <div className="card p-3 flex items-center justify-between gap-3 text-xs">
      <span className="text-neutral-500">Waiting for location permission</span>
      <button
        type="button"
        onClick={captureLocation}
        className="text-[11px] text-brand-700 hover:text-black transition shrink-0"
      >
        Allow
      </button>
      {location && (
        <button
          type="button"
          onClick={clear}
          className="text-[11px] text-neutral-400 hover:text-black transition shrink-0"
        >
          Clear
        </button>
      )}
    </div>
  );
}
