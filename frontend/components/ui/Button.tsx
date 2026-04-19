"use client";

import { forwardRef, type ButtonHTMLAttributes } from "react";

// Single source of truth for every action button in the app. Consistent
// sizing and coloring across the cockpit - primary CTAs use the navy brand
// accent, secondary buttons are outlined neutral, ghost buttons are
// text-only. All variants share the same rounded-full shape and transition.

export type ButtonVariant = "primary" | "secondary" | "ghost";
export type ButtonSize = "sm" | "md" | "lg" | "icon";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

// One glassy premium theme for every button. Translucent white over backdrop
// blur, hair-line neutral border, subtle lift via layered shadow + inner
// highlight. Variants differ only in emphasis — primary sits brighter/more
// opaque, secondary sits quieter, ghost drops the surface entirely on rest.
const BASE =
  "inline-flex items-center justify-center gap-2 rounded-full font-medium transition whitespace-nowrap text-black " +
  "backdrop-blur-xl ring-1 ring-black/5 " +
  "shadow-[inset_0_1px_0_rgba(255,255,255,0.6),0_1px_2px_rgba(0,0,0,0.04),0_6px_16px_-6px_rgba(0,0,0,0.12)] " +
  "hover:ring-black/10 hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.75),0_2px_6px_rgba(0,0,0,0.06),0_10px_24px_-8px_rgba(0,0,0,0.18)] " +
  "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:shadow-none " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-black/20 focus-visible:ring-offset-2";

const SIZES: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
  lg: "px-5 py-2.5 text-sm",
  // Square icon-only pill — matches `md`'s vertical rhythm without horizontal
  // text padding. Use for sidebar toggles, close chips, etc.
  icon: "h-9 w-9 p-0 text-sm",
};

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "bg-white/80 border border-white/60 hover:bg-white/95 hover:border-neutral-300",
  secondary:
    "bg-white/60 border border-white/50 hover:bg-white/85 hover:border-neutral-300",
  ghost:
    "bg-white/30 border border-transparent hover:bg-white/70 hover:border-white/60 text-neutral-600 hover:text-black",
};

// Share the exact same class string with non-button elements (anchor tags
// styled as buttons, etc.) so the design stays in one place.
export function buttonClasses(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  extra = "",
): string {
  return `${BASE} ${SIZES[size]} ${VARIANTS[variant]} ${extra}`;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "primary",
      size = "md",
      className = "",
      type = "button",
      ...rest
    },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type}
        className={`${BASE} ${SIZES[size]} ${VARIANTS[variant]} ${className}`}
        {...rest}
      />
    );
  },
);
