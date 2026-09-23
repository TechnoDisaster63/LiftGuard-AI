/** @type {import('next').NextConfig} */

// Proxy mode (used by the Codespaces setup): when LIFTGUARD_BACKEND_URL is
// set, the Next server forwards /api/* and /ws/* to the backend, so the
// browser only ever talks to the frontend's own origin. Build the frontend
// with NEXT_PUBLIC_API_BASE="" in that case. Without it, the browser calls
// the backend directly at NEXT_PUBLIC_API_BASE (default http://localhost:8000).
const backend = process.env.LIFTGUARD_BACKEND_URL;

const nextConfig = {
  reactStrictMode: true,
  ...(backend
    ? {
        async rewrites() {
          return [
            { source: "/api/:path*", destination: `${backend}/api/:path*` },
            { source: "/ws/:path*", destination: `${backend}/ws/:path*` },
          ];
        },
      }
    : {}),
};

module.exports = nextConfig;
