/** @type {import('next').NextConfig} */
const nextConfig = {
  // standalone output → the multi-stage Docker image stays slim (~120MB
  // vs ~500MB): Next traces the exact files needed and copies only those.
  output: "standalone",
  reactStrictMode: true,
  // The BFF (app/api/**/route.ts) talks to the FastAPI backend server-side via
  // API_BASE_URL (NOT NEXT_PUBLIC_ — the backend URL stays off the browser).
  // Nothing to expose here; documented for the next reader.
  images: {
    // Anime cover art (UI redesign phase 2) is served from MyAnimeList's CDN.
    // next/image optimizes it through the server, so we must allowlist the host.
    remotePatterns: [
      { protocol: "https", hostname: "cdn.myanimelist.net" },
    ],
  },
};

export default nextConfig;
