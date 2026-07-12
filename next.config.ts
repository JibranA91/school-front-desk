import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lean, self-contained server bundle for the Docker image.
  output: "standalone",
  // Pin the workspace root so Next doesn't infer it from a stray lockfile
  // higher up the home directory.
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
