const path = require('path');

const PRODUCTION_API_URL = "https://lenny-podcast-assistant.onrender.com";
const isDev = process.env.NODE_ENV === "development";
const envUrl = (process.env.NEXT_PUBLIC_API_URL || "").trim();

let API_BASE_URL = PRODUCTION_API_URL;
if (isDev) {
  API_BASE_URL = envUrl || "http://localhost:8000";
} else if (envUrl && !envUrl.includes("localhost") && !envUrl.includes("127.0.0.1")) {
  API_BASE_URL = envUrl;
}

API_BASE_URL = API_BASE_URL.replace(/\/+$/, "");

console.log("API Base URL:", API_BASE_URL);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: path.join(__dirname),
  async rewrites() {
    return [
      {
        source: "/api/proxy/:path*",
        destination: `${API_BASE_URL}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
