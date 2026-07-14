"use client";

import { SessionProvider } from "next-auth/react";

/** Client context so components can read/refresh the session (used by the
 *  theme toggle's useSession().update()). */
export default function Providers({ children }: { children: React.ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
