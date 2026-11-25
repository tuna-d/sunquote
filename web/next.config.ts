import type { NextConfig } from "next";

// The API's address. Next reads it when it builds (the rewrite is baked into the routes
// manifest), so set it for `next build` too. The default is the API's own default port.
const apiUrl = (process.env.SUNQUOTE_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  // The browser calls `/api/...` on the web app's own origin; Next forwards it to the API.
  // No CORS: the API never sees a cross-origin request.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
  async redirects() {
    return [{ source: "/", destination: "/quotes", permanent: false }];
  },
  output: "standalone",
};

export default nextConfig;
