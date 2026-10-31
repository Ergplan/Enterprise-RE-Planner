"use client";

import { useEffect } from "react";

type ErgOSRuntime = { mount: (root?: Element | Document) => void };

// Fills data-icon spans and folder shapes once harmony.js has loaded and after each render.
export function ErgOSMount() {
  useEffect(() => {
    let tries = 0;
    const run = () => {
      const e = (window as unknown as { ErgOS?: ErgOSRuntime }).ErgOS;
      if (e) e.mount(document);
      else if (tries++ < 40) setTimeout(run, 50);
    };
    run();
  });
  return null;
}
