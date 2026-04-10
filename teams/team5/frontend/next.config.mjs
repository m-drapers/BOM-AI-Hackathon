/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // In dev, proxy /api/* to the local backend.
    // In production (Docker/Caddy), the reverse proxy handles this.
    const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
