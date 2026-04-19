"use client";

// Decorative ruler strip. A row of hairline tick marks with every Nth tick
// accented, giving the instrument-panel visual vocabulary without adding
// any DOM weight (renders via two stacked linear-gradients). Use above a
// section header or below a card title to signal "measurement" and to make
// the page feel deliberately engineered rather than template-generic.

interface Props {
  variant?: "plain" | "keyed";
  /** Tailwind width + alignment wrapper classes. Example: "w-24 opacity-60". */
  className?: string;
}

export function TickRuler({ variant = "keyed", className = "" }: Props) {
  const cls = variant === "plain" ? "tick-ruler" : "tick-ruler-keyed";
  return <div aria-hidden className={`${cls} ${className}`} />;
}
