"use client";

import { useMemo } from "react";
import { GoogleMap, Marker, useJsApiLoader } from "@react-google-maps/api";
import type { TrialSite } from "@/lib/types";
import type { UserLocation } from "@/lib/geo";

const MAP_STYLE = [
  { elementType: "geometry", stylers: [{ color: "#f5f5f5" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#ffffff" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#666666" }] },
  {
    featureType: "road",
    elementType: "geometry",
    stylers: [{ color: "#ffffff" }],
  },
  {
    featureType: "water",
    elementType: "geometry",
    stylers: [{ color: "#e7e7e7" }],
  },
  {
    featureType: "administrative",
    elementType: "geometry",
    stylers: [{ color: "#c8c8c8" }],
  },
  {
    featureType: "poi",
    stylers: [{ visibility: "off" }],
  },
];

export function TrialMap({
  sites,
  selected,
  onSelect,
  userLocation,
}: {
  sites: TrialSite[];
  selected: string | null;
  onSelect: (nct: string | null) => void;
  userLocation?: UserLocation | null;
}) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
  const { isLoaded } = useJsApiLoader({
    id: "nv-map-loader",
    googleMapsApiKey: apiKey ?? "",
  });

  const filtered = useMemo(
    () =>
      sites.filter(
        (s) =>
          s.lat !== null &&
          s.lng !== null &&
          (selected === null || s.nct_id === selected),
      ),
    [sites, selected],
  );

  // Priority: center on the user when we know where they are. Otherwise
  // average the filtered sites. Fallback to a US centroid if we know nothing.
  const center = useMemo(() => {
    if (userLocation) {
      return { lat: userLocation.lat, lng: userLocation.lng };
    }
    if (!filtered.length) return { lat: 39.5, lng: -98.35 };
    const avg = filtered.reduce(
      (acc, s) => ({
        lat: acc.lat + (s.lat ?? 0),
        lng: acc.lng + (s.lng ?? 0),
      }),
      { lat: 0, lng: 0 },
    );
    return {
      lat: avg.lat / filtered.length,
      lng: avg.lng / filtered.length,
    };
  }, [filtered, userLocation]);

  // Default zoom: tighter when the user has a location OR when only one
  // trial is filtered in; otherwise a continental view.
  const zoom = userLocation ? 6 : filtered.length === 1 ? 10 : 3;

  if (!apiKey) {
    return (
      <div className="card p-5">
        <h3 className="eyebrow mb-2">Trial sites</h3>
        <p className="text-xs text-neutral-600 mb-2">
          Set{" "}
          <code className="text-black">NEXT_PUBLIC_GOOGLE_MAPS_API_KEY</code> to
          render the interactive map. Showing the first 12 sites as a list.
        </p>
        <ul className="text-sm text-neutral-800 space-y-1 max-h-80 overflow-y-auto">
          {sites.slice(0, 12).map((s, i) => (
            <li
              key={`${s.nct_id}-${i}`}
              className={`truncate ${selected && selected !== s.nct_id ? "opacity-40" : ""}`}
            >
              <span className="mono-tag">{s.nct_id}</span> {s.facility} ·{" "}
              {s.city}, {s.state}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (!isLoaded) {
    return (
      <div className="card p-5 text-neutral-500 text-sm">Loading map…</div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 text-xs text-neutral-600 border-b border-neutral-100">
        <span>
          Trial sites ({filtered.length}
          {selected ? ` · filtered ${selected}` : ""})
        </span>
        {selected && (
          <button
            onClick={() => onSelect(null)}
            className="text-brand-700 hover:text-black"
          >
            Clear filter
          </button>
        )}
      </div>
      <GoogleMap
        mapContainerStyle={{ width: "100%", height: "22rem" }}
        zoom={zoom}
        center={center}
        options={{
          disableDefaultUI: true,
          zoomControl: true,
          styles: MAP_STYLE,
        }}
      >
        {filtered.map((s, i) => (
          <Marker
            key={`${s.nct_id}-${i}`}
            position={{ lat: s.lat!, lng: s.lng! }}
            onClick={() => onSelect(s.nct_id)}
            title={`${s.nct_id}\n${s.facility}\n${s.city}, ${s.state}`}
          />
        ))}
        {userLocation && (
          <Marker
            position={{ lat: userLocation.lat, lng: userLocation.lng }}
            title={userLocation.label || "You are here"}
            // Distinct styling so the user pin stands out from trial-site pins.
            icon={{
              path: "M 0,-7 7,7 0,4 -7,7 z",
              fillColor: "#0b2545",
              fillOpacity: 1,
              strokeColor: "#ffffff",
              strokeWeight: 2,
              scale: 1.2,
            }}
            zIndex={1000}
          />
        )}
      </GoogleMap>
    </div>
  );
}
