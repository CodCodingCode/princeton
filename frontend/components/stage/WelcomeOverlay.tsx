"use client";

// Minimal welcome state: the avatar still-frame is the hero, and a caption-
// pill-styled button floats at the bottom. Clicking it fires `onBegin`, which
// boots the LiveAvatar and queues the greeting (see app/page.tsx handleBegin).
// After click the button just fades out - no "Connecting…" label, since that
// would overlap the live caption pill once the avatar starts speaking.

import { useState } from "react";

interface Props {
  onBegin: () => void;
  busy?: boolean;
  // Externally-driven hide flag. When the parent changes phase immediately
  // on click, it sets this to true so the button fades out in parallel with
  // the phase transition rather than after it.
  hidden?: boolean;
}

export function WelcomeOverlay({
  onBegin,
  busy,
  hidden: externalHidden,
}: Props) {
  const [clicked, setClicked] = useState(false);
  const hidden = busy || clicked || externalHidden;

  const handle = () => {
    if (hidden) return;
    setClicked(true);
    onBegin();
  };

  return (
    <div className="absolute inset-0 pointer-events-none">
      <div className="absolute bottom-24 left-0 right-0 flex justify-center px-6">
        <button
          onClick={handle}
          disabled={hidden}
          aria-hidden={hidden}
          className={`bg-black/65 backdrop-blur-md text-white rounded-xl px-6 py-3 text-sm md:text-base leading-snug text-center ring-1 ring-white/15 shadow-lg shadow-black/30 transition-opacity duration-500 ease-out cursor-pointer hover:bg-black/80 hover:ring-white/25 ${
            hidden
              ? "opacity-0 pointer-events-none"
              : "opacity-100 pointer-events-auto"
          }`}
        >
          Begin
        </button>
      </div>
    </div>
  );
}
