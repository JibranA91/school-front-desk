"use client";

import { useEffect } from "react";

/**
 * Publishes the visual-viewport height as a `--vvh` CSS variable so the
 * full-screen mobile layouts can size to the space that's actually visible.
 *
 * On mobile the on-screen keyboard shrinks the *visual* viewport but not
 * `100dvh`/`100vh`, so a fixed-height app gets scrolled (header pushed off) to
 * keep the focused input in view. Tracking visualViewport.height instead makes
 * the app shrink to sit above the keyboard, header intact. Renders nothing.
 */
export default function ViewportSync() {
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const root = document.documentElement;
    const apply = () => root.style.setProperty("--vvh", `${vv.height}px`);
    apply();
    vv.addEventListener("resize", apply);
    vv.addEventListener("scroll", apply);
    return () => {
      vv.removeEventListener("resize", apply);
      vv.removeEventListener("scroll", apply);
      root.style.removeProperty("--vvh");
    };
  }, []);

  return null;
}
