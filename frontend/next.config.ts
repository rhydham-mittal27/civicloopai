import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // /api/v1/* is served by app/api/v1/[...path]/route.ts, which keeps the sign-in token in an httpOnly cookie
  // and forwards to BACKEND_URL (default http://127.0.0.1:8000).
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
