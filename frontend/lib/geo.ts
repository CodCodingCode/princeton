// Lightweight geo helpers. All distances returned in miles since that's what
// the UI renders (kilometres are a single flag flip when we want them).

export interface LatLng {
  lat: number;
  lng: number;
}

export interface UserLocation extends LatLng {
  label?: string; // human-readable city/ZIP shown in the UI
  source: "browser" | "geocoded" | "manual";
}

const EARTH_RADIUS_MI = 3958.7613;

export function haversineMiles(a: LatLng, b: LatLng): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_MI * Math.asin(Math.sqrt(s));
}

/**
 * Closest site (by straight-line distance) to the user. Returns null when
 * the user has no location set, or none of the sites have lat/lng.
 */
export function nearestSite<
  T extends { lat: number | null; lng: number | null },
>(user: UserLocation | null, sites: T[]): { site: T; miles: number } | null {
  if (!user) return null;
  let best: { site: T; miles: number } | null = null;
  for (const s of sites) {
    if (s.lat == null || s.lng == null) continue;
    const miles = haversineMiles(user, { lat: s.lat, lng: s.lng });
    if (!best || miles < best.miles) {
      best = { site: s, miles };
    }
  }
  return best;
}

/**
 * Format miles for display. <10 miles -> one decimal, otherwise integer.
 * Rough approximations are appropriate for "where's the nearest trial site"
 * since the point is to find something actionable, not plan a route.
 */
export function formatMiles(miles: number): string {
  if (miles < 0.1) return "< 0.1 mi";
  if (miles < 10) return `${miles.toFixed(1)} mi`;
  return `${Math.round(miles)} mi`;
}
