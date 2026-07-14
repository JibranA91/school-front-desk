import { auth } from "@/auth";

export default auth((req) => {
  const { nextUrl } = req;
  const isLoggedIn = !!req.auth;
  const role = req.auth?.user?.role;
  const path = nextUrl.pathname;

  // Login page: bounce already-authenticated users to their home.
  if (path.startsWith("/login")) {
    if (isLoggedIn) {
      const dest = role === "operator" ? "/operator" : "/";
      return Response.redirect(new URL(dest, nextUrl));
    }
    return;
  }

  // Everything else requires a session.
  if (!isLoggedIn) {
    return Response.redirect(new URL("/login", nextUrl));
  }

  // Operator console is operator-only.
  if (path.startsWith("/operator") && role !== "operator") {
    return Response.redirect(new URL("/", nextUrl));
  }

  // Operators don't use the parent chat — the front desk is their console.
  if (role === "operator" && path === "/") {
    return Response.redirect(new URL("/operator", nextUrl));
  }
});

export const config = {
  // Run on all routes except API (incl. /api/auth), Next internals, and public
  // assets (favicon, svgs, the PWA manifest — the browser fetches it unauthed).
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|manifest.webmanifest|.*\\.svg$).*)",
  ],
};
