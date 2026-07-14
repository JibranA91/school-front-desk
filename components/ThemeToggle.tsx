"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";

type Theme = "light" | "dark";

/** Sun/moon toggle that flips the app between light and dark. The choice is
 *  applied instantly (data-theme on <html>), persisted to the DB for this user,
 *  and folded back into the session token so SSR stays in sync on reload. */
export default function ThemeToggle() {
  const { update } = useSession();
  const [theme, setTheme] = useState<Theme>("light");
  const [busy, setBusy] = useState(false);

  // SSR stamped the real theme on <html>; adopt it after mount (keeps the
  // initial client render matching the server's "light" default — no mismatch).
  useEffect(() => {
    const current = document.documentElement.dataset.theme;
    if (current === "dark") setTheme("dark");
  }, []);

  const toggle = async () => {
    if (busy) return;
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    // Apply immediately for instant feedback.
    document.documentElement.dataset.theme = next;
    document.documentElement.style.colorScheme = next;
    setBusy(true);
    try {
      await fetch("/api/my/theme", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme: next }),
      });
      // Refresh the JWT so a full reload renders in the new theme (no flash).
      await update({ theme: next });
    } catch {
      /* the DB write is best-effort; the live UI already reflects the choice */
    } finally {
      setBusy(false);
    }
  };

  const isDark = theme === "dark";
  const label = isDark ? "Switch to light mode" : "Switch to dark mode";

  return (
    <button
      onClick={toggle}
      className="fd-ghost fd-theme-toggle"
      aria-label={label}
      title={label}
      style={{
        border: "1px solid var(--fd-border)",
        background: "transparent",
        color: "var(--fd-faint)",
        borderRadius: 999,
        width: 34,
        height: 34,
        display: "grid",
        placeItems: "center",
        cursor: "pointer",
        transition: "all .15s",
        flexShrink: 0,
      }}
    >
      {isDark ? (
        // Sun — currently dark, click to go light.
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
        </svg>
      ) : (
        // Moon — currently light, click to go dark.
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}
