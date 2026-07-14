import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import { auth } from "@/auth";
import Providers from "@/components/Providers";
import "./globals.css";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-jakarta",
});

export const metadata: Metadata = {
  title: "AI Front Desk — Sunnyside Early Learning",
  description:
    "An AI front desk for early-education centers: trustworthy, grounded answers for parents and a control center for operators.",
  manifest: "/manifest.webmanifest",
  // iOS: launch chrome-free (no Safari address bar) when added to the home screen.
  appleWebApp: {
    capable: true,
    title: "Sunnyside",
    statusBarStyle: "default",
  },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Read the signed-in user's saved preference from the session (JWT — no DB
  // hit) and stamp it on <html> during SSR, so the first paint is already in
  // the right theme (no flash). The toggle updates this attribute live.
  const session = await auth();
  const theme = session?.user?.theme === "dark" ? "dark" : "light";

  return (
    <html
      lang="en"
      data-theme={theme}
      style={{ colorScheme: theme }}
      className={jakarta.variable}
    >
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
