"use client";

// Horizontal gauge primitive. Renders a hairline bar with a value marker
// and optional range-shading zones. Designed to sit inline next to a
// clinical metric: "TMB · 12.3 mut/Mb" gets a compact bar showing where
// that value lands on the 0-20 mut/Mb axis with a shaded "TMB-high" band.
//
// Deliberately small surface: just `value`, `min`, `max`, and optional
// `bands` for zone shading. Ticks at min / max. No grid, no legend.

interface Band {
  from: number;
  to: number;
  /** CSS color (can use rgba / hex / tailwind arbitrary via className). */
  fill: string;
  /** Optional short label rendered above the band mid-point. */
  label?: string;
}

interface Props {
  value: number | null;
  min: number;
  max: number;
  unit?: string;
  bands?: Band[];
  /** Short label shown at left, e.g. "Breslow". */
  label?: string;
  /** Reference threshold rendered as a thin vertical line. */
  threshold?: { value: number; label?: string };
  className?: string;
}

function pct(v: number, min: number, max: number) {
  if (max <= min) return 0;
  return Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100));
}

export function Gauge({
  value,
  min,
  max,
  unit,
  bands,
  label,
  threshold,
  className = "",
}: Props) {
  const hasValue = value !== null && Number.isFinite(value);
  const markerPct = hasValue ? pct(value as number, min, max) : 0;
  const threshPct =
    threshold !== undefined ? pct(threshold.value, min, max) : null;

  return (
    <div className={`font-mono ${className}`}>
      {(label || hasValue) && (
        <div className="flex items-baseline justify-between mb-1.5">
          {label && (
            <span className="text-[10px] uppercase tracking-[0.18em] text-neutral-500 font-semibold">
              {label}
            </span>
          )}
          <span className="text-[11px] tabular-nums text-black font-medium">
            {hasValue ? value : "-"}
            {unit && hasValue ? (
              <span className="text-neutral-400 ml-0.5">{unit}</span>
            ) : null}
          </span>
        </div>
      )}

      <div className="relative h-1.5 w-full bg-neutral-200/70 rounded-full overflow-hidden">
        {/* Shaded bands (clinical reference zones). */}
        {bands?.map((b, i) => {
          const left = pct(b.from, min, max);
          const right = pct(b.to, min, max);
          return (
            <span
              key={i}
              aria-hidden
              className="absolute inset-y-0 rounded-full"
              style={{
                left: `${left}%`,
                width: `${Math.max(right - left, 0.4)}%`,
                background: b.fill,
              }}
            />
          );
        })}

        {/* Threshold line. */}
        {threshPct !== null && (
          <span
            aria-hidden
            className="absolute inset-y-0 w-px bg-black/40"
            style={{ left: `${threshPct}%` }}
          />
        )}

        {/* Value marker: a thick black bar rather than a dot so it reads on
            top of shaded bands without a halo. */}
        {hasValue && (
          <span
            aria-hidden
            className="absolute top-[-3px] bottom-[-3px] w-[3px] bg-black rounded-sm shadow-[0_0_0_1px_rgba(255,255,255,0.8)]"
            style={{ left: `calc(${markerPct}% - 1.5px)` }}
          />
        )}
      </div>

      {/* Tick scale: min · (optional threshold label) · max. */}
      <div className="flex items-center justify-between mt-1 text-[9px] tabular-nums text-neutral-400">
        <span>{min}</span>
        {threshold?.label && (
          <span
            className="relative text-neutral-500"
            style={{ marginLeft: `${threshPct}%` }}
          >
            {threshold.label}
          </span>
        )}
        <span>{max}</span>
      </div>
    </div>
  );
}
