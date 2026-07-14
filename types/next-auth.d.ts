import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface User {
    role?: string;
    title?: string | null;
    theme?: string;
  }

  interface Session {
    user: {
      id?: string;
      role?: string;
      title?: string | null;
      theme?: string;
    } & DefaultSession["user"];
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    role?: string;
    title?: string | null;
    theme?: string;
  }
}
