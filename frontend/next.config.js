/** @type {import('next').NextConfig} */

// Proxy mode (used by the Codespaces setup): when LIFTGUARD_BACKEND_URL is
// set, the Next server forwards /api/* and /ws/* to the backend, so the
// browser only ever talks to the frontend's own origin. Build the frontend
// with NEXT_PUBLIC_API_BASE="" in that case. Without it, the browser calls
// the backend directly at NEXT_PUBLIC_API_BASE (default http://localhost:8000).
const backend = process.env.LIFTGUARD_BACKEND_URL;

// Static export (used by the Hugging Face Space image): the backend serves
// the built pages itself, so the browser, /api and /ws share one origin and
// no Node server runs in production.
const staticExport = process.env.LIFTGUARD_STATIC_EXPORT === "1";

const nextConfig = {
  reactStrictMode: true,
  ...(staticExport ? { output: "export", trailingSlash: true, images: { unoptimized: true } } : {}),
  ...(backend && !staticExport
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
