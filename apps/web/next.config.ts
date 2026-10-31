import type { NextConfig } from "next";

// The browser talks to the API through this origin (/api/*), so a PDF opened at /api/documents/{id}#page=N
// is same-origin and needs no CORS. API_URL is the API as the web server sees it.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const config: NextConfig = {
  output: "standalone",
  // a second dev server (the Stage 7 end-to-end) builds into its own folder
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // A bill takes billx one to three minutes to read; the /api proxy must wait for it.
  experimental: { proxyTimeout: 600_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default config;
