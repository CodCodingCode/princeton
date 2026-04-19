"use client";

import { useEffect, useRef, useState } from "react";
import type { PatientCase } from "@/lib/types";
import type { UserLocation } from "@/lib/geo";
import { TrialList } from "@/components/TrialList";
import { TrialMap } from "@/components/TrialMap";
import {
  readStoredLocation,
  writeStoredLocation,
} from "@/components/LocationPrompt";

type LocationStatus =
  | "idle"
  | "locating"
  | "ready"
  | "denied"
  | "unsupported"
  | "error";

// Ask the browser for precise coordinates. Triggers the native permission
// prompt on first use; cached by the browser on subsequent visits.
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

// IP-based fallback. Used only when the native prompt is denied, unsupported,
// or times out. Accuracy is roughly city-level,good enough to sort trial
// sites by rough distance even without the user sharing GPS.
async function lookupIpLocation(): Promise<UserLocation | null> {
  try {
    const res = await fetch("https://ipapi.co/json/", { cache: "no-store" });
    if (!res.ok) return null;
    const data = (await res.json()) as {
      latitude?: number;
      longitude?: number;
      city?: string;
      region?: string;
      country_name?: string;
    };
    if (
      typeof data.latitude !== "number" ||
      typeof data.longitude !== "number"
    ) {
      return null;
    }
    const label =
      [data.city, data.region || data.country_name]
        .filter(Boolean)
        .join(", ") || undefined;
    return {
      lat: data.latitude,
      lng: data.longitude,
      label,
      source: "geocoded",
    };
  } catch {
    return null;
  }
}

export function TrialsTab({ caseData }: { caseData: PatientCase }) {
  const [selectedNct, setSelectedNct] = useState<string | null>(null);
  const [userLocation, setUserLocation] = useState<UserLocation | null>(null);
  const [locationStatus, setLocationStatus] = useState<LocationStatus>("idle");
  // Guard so the one-shot "auto-acquire on mount" effect doesn't fire twice
  // (StrictMode double-invokes effects in dev).
  const acquiredRef = useRef(false);

  // Auto-acquire location: localStorage → native geolocation → IP fallback.
  useEffect(() => {
    if (acquiredRef.current) return;
    acquiredRef.current = true;

    const cached = readStoredLocation(caseData.case_id);
    if (cached) {
      setUserLocation(cached);
      setLocationStatus("ready");
      return;
    }

    let cancelled = false;
    (async () => {
      setLocationStatus("locating");
      try {
        const pos = await requestBrowserLocation();
        if (cancelled) return;
        const loc: UserLocation = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          source: "browser",
        };
        writeStoredLocation(caseData.case_id, loc);
        setUserLocation(loc);
        setLocationStatus("ready");
      } catch (e) {
        // Fall back to IP-based geolocation. Keeps sorting useful even when
        // the native prompt is denied or unavailable.
        const ip = await lookupIpLocation();
        if (cancelled) return;
        if (ip) {
          writeStoredLocation(caseData.case_id, ip);
          setUserLocation(ip);
          setLocationStatus("ready");
          return;
        }
        if (e instanceof GeolocationPositionError && e.code === 1) {
          setLocationStatus("denied");
        } else if (e instanceof Error && /not supported/i.test(e.message)) {
          setLocationStatus("unsupported");
        } else {
          setLocationStatus("error");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [caseData.case_id]);

  return (
    <div className="space-y-5">
      {locationStatus === "locating" && (
        <div className="card px-3 py-2 flex items-center gap-2 text-xs text-neutral-600">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-brand-700 animate-pulse" />
          <span>Finding your location to rank trials by nearest site…</span>
        </div>
      )}
      {userLocation && (
        <div className="card px-3 py-2 flex items-center gap-2 text-xs text-neutral-600">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500" />
          <span>
            Trials sorted by distance from{" "}
            <span className="text-black">
              {userLocation.label ??
                `${userLocation.lat.toFixed(2)}, ${userLocation.lng.toFixed(2)}`}
            </span>
          </span>
        </div>
      )}

      <TrialMap
        sites={caseData.trial_sites}
        selected={selectedNct}
        onSelect={setSelectedNct}
        userLocation={userLocation}
      />

      <TrialList
        matches={caseData.trial_matches}
        sites={caseData.trial_sites}
        selected={selectedNct}
        onSelect={setSelectedNct}
        userLocation={userLocation}
      />
    </div>
  );
}
