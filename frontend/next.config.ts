import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep Turbopack rooted on the frontend app so the parent lockfile
  // doesn't get treated as the project root (breaks the RSC client manifest).
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
