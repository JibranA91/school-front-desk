import type { MetadataRoute } from "next";

// Makes the app installable ("Add to Home Screen"). Launched from the home
// screen it runs in standalone display mode — no browser address bar / chrome,
// a true full-screen app.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Sunnyside Front Desk",
    short_name: "Sunnyside",
    description: "AI front desk for Sunnyside Early Learning Center.",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#5463D6",
  };
}
