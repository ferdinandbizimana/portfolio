import type { NextConfig } from "next";

// In Docker, Caddy sends /api/* to the backend before it reaches Next.js.
// This rewrite only matters when running `pnpm dev` (or the app on port 3000)
// directly: it forwards /api/* to the backend so the browser still talks to a
// single origin. The destination is fixed at build time.
const apiUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
