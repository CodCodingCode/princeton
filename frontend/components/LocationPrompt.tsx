"use client";

// Patient-location capture for the Trials tab.
//
// UX flow:
//   1. Show a compact card offering "Use my location" + a text input.
//   2. "Use my location" -> navigator.geolocation -> precise lat/lng.
//   3. Text input (city or ZIP) -> Google Maps Geocoder (JS SDK, loaded
//      already for the TrialMap) -> lat/lng.
//   4. Persist to localStorage keyed by caseId so a refresh keeps the
//      distance sort intact.
//
// Parent owns the `UserLocation` state; this component calls `onChange`
// when a location is captured or cleared.

import { useJsApiLoader } from "@react-google-maps/api";
import { useState } from "react";
import type { UserLocation } from "@/lib/geo";

interface Props {
  caseId: string;
  location: UserLocation | null;
  onChange: (loc: UserLocation | null) => void;
}

export function locationStorageKey(caseId: string): string {
  return `neovax:location:${caseId}`;
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

export function LocationPrompt({ caseId, location, onChange }: Props) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
  const { isLoaded: mapsReady } = useJsApiLoader({
    id: "nv-map-loader",
    googleMapsApiKey: apiKey ?? "",
  });

  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (loc: UserLocation | null) => {
    writeStoredLocation(caseId, loc);
    onChange(loc);
  };

  async function useBrowserLocation() {
    setError(null);
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setError("Your browser doesn't support location lookup.");
      return;
    }
    setBusy(true);
    try {
      const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          maximumAge: 5 * 60 * 1000,
          timeout: 8000,
        });
      });
      update({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        source: "browser",
      });
    } catch (e) {
      const msg = e instanceof GeolocationPositionError ? e.message : String(e);
      setError(
        msg ||
          "Couldn't read your location. Try entering a city or ZIP instead.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function geocodeQuery() {
    const q = query.trim();
    if (!q) return;
    setError(null);
    if (!mapsReady || typeof google === "undefined") {
      setError("Map service isn't ready yet. Try again in a moment.");
      return;
    }
    setBusy(true);
    try {
      const geocoder = new google.maps.Geocoder();
      const { results } = await geocoder.geocode({ address: q });
      if (!results.length) {
        setError(`No match for "${q}". Try a city, ZIP, or address.`);
        return;
      }
      const best = results[0];
      const loc = best.geometry.location;
      update({
        lat: loc.lat(),
        lng: loc.lng(),
        label: best.formatted_address || q,
        source: "geocoded",
      });
      setQuery("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (location) {
    return (
      <div className="card p-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="eyebrow mb-0.5">Your location</div>
          <div className="text-sm text-black truncate">
            {location.label ||
              `${location.lat.toFixed(3)}, ${location.lng.toFixed(3)}`}
          </div>
          <div className="text-[11px] text-neutral-500 mt-0.5">
            {location.source === "browser"
              ? "From your browser. Trials sorted by distance."
              : location.source === "geocoded"
                ? "From your typed address."
                : "Manual entry."}
          </div>
        </div>
        <button
          type="button"
          onClick={() => update(null)}
          className="text-xs text-neutral-500 hover:text-black transition shrink-0"
        >
          Change
        </button>
      </div>
    );
  }

  return (
    <div className="card p-4">
      <div className="eyebrow mb-1">Find trials near you</div>
      <p className="text-xs text-neutral-500 mb-3">
        We'll sort matched trials by distance to the nearest recruiting site.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={useBrowserLocation}
          disabled={busy}
          className="px-4 py-1.5 rounded-full bg-black text-white text-xs font-medium hover:bg-brand-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {busy ? "Locating…" : "Use my location"}
        </button>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            geocodeQuery();
          }}
          className="flex items-center gap-2 flex-1 min-w-[220px]"
        >
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="or enter city or ZIP"
            disabled={busy}
            className="flex-1 text-xs border border-neutral-200 rounded-full px-3 py-1.5 focus:outline-none focus:border-black disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={busy || !query.trim()}
            className="px-3 py-1.5 rounded-full border border-neutral-300 text-xs text-neutral-700 hover:border-black hover:text-black transition disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Apply
          </button>
        </form>
      </div>
      {error && <div className="mt-2 text-[11px] text-red-600">{error}</div>}
    </div>
  );
}
