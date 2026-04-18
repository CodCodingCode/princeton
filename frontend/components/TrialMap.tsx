"use client";

import { useMemo } from "react";
import { GoogleMap, Marker, useJsApiLoader } from "@react-google-maps/api";
import type { TrialSite } from "@/lib/types";

const MAP_STYLE = [
  { elementType: "geometry", stylers: [{ color: "#0f172a" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0f172a" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#94a3b8" }] },
  {
    featureType: "road",
    elementType: "geometry",
    stylers: [{ color: "#1e293b" }],
  },
  {
    featureType: "water",
    elementType: "geometry",
    stylers: [{ color: "#020617" }],
  },
  {
    featureType: "administrative",
    elementType: "geometry",
    stylers: [{ color: "#475569" }],
  },
];

export function TrialMap({
  sites,
  selected,
  onSelect,
}: {
  sites: TrialSite[];
  selected: string | null;
  onSelect: (nct: string | null) => void;
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

  const center = useMemo(() => {
    if (!filtered.length) return { lat: 39.5, lng: -98.35 }; // US centroid
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
  }, [filtered]);

  if (!apiKey) {
    return (
      <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
        <h3 className="text-sm font-semibold text-teal-400 mb-2">
          Trial sites
        </h3>
        <p className="text-xs text-ink-400 mb-2">
          Set{" "}
          <code className="text-ink-300">NEXT_PUBLIC_GOOGLE_MAPS_API_KEY</code>{" "}
          to render the interactive map. Showing the first 12 sites as a list.
        </p>
        <ul className="text-sm text-ink-200 space-y-1 max-h-80 overflow-y-auto">
          {sites.slice(0, 12).map((s, i) => (
            <li
              key={`${s.nct_id}-${i}`}
              className={`truncate ${selected && selected !== s.nct_id ? "opacity-40" : ""}`}
            >
              <span className="text-teal-400 font-mono text-xs">
                {s.nct_id}
              </span>{" "}
              {s.facility} · {s.city}, {s.state}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (!isLoaded) {
    return (
      <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-6 text-ink-500 text-sm">
        Loading map…
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/40 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 text-xs text-ink-400 border-b border-ink-800">
        <span>
          Trial sites ({filtered.length}
          {selected ? ` · filtered ${selected}` : ""})
        </span>
        {selected && (
          <button
            onClick={() => onSelect(null)}
            className="text-teal-400 hover:text-teal-300"
          >
            Clear filter
          </button>
        )}
      </div>
      <GoogleMap
        mapContainerStyle={{ width: "100%", height: "22rem" }}
        zoom={filtered.length === 1 ? 10 : 3}
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
      </GoogleMap>
    </div>
  );
}
