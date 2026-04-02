import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [{ source: "/gallery", destination: "/", permanent: true }];
  },
};

export default nextConfig;
