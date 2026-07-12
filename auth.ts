import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8001";
const AUTH_SHARED_SECRET =
  process.env.AUTH_SHARED_SECRET ?? "dev-shared-secret-change-me";

export const { handlers, signIn, signOut, auth } = NextAuth({
  trustHost: true,
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      // Delegate credential verification to the FastAPI service (which holds
      // the bcrypt hashes). We never store or hash passwords in the web tier.
      authorize: async (creds) => {
        if (!creds?.email || !creds?.password) return null;
        try {
          const res = await fetch(`${API_BASE_URL}/auth/login`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Internal-Secret": AUTH_SHARED_SECRET,
            },
            body: JSON.stringify({
              email: creds.email,
              password: creds.password,
            }),
          });
          if (!res.ok) return null;
          const u = await res.json();
          return {
            id: u.id,
            email: u.email,
            name: u.name,
            role: u.role,
            title: u.title ?? null,
          };
        } catch {
          return null;
        }
      },
    }),
  ],
  callbacks: {
    jwt({ token, user }) {
      if (user) {
        token.role = user.role;
        token.title = user.title ?? null;
      }
      return token;
    },
    session({ session, token }) {
      if (session.user) {
        session.user.role = token.role;
        session.user.title = token.title ?? null;
      }
      return session;
    },
  },
});
