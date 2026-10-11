import type { NextConfig } from "next";

// The dashboard is a client-rendered, polling UI. Cache Components / partial
// prefetching are left off on purpose: every page reads live data in the browser.
const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Self-contained server in .next/standalone for the production image (frontend/Dockerfile, WS0 R5).
  output: "standalone",
  turbopack: {
    // pin the workspace root to frontend/ (a parent pnpm-workspace.yaml would otherwise confuse it)
    root: __dirname,
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
