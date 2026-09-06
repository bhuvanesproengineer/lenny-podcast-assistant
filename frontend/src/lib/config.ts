/**
 * Centralized API Configuration for Lenny Growth Assistant Frontend
 *
 * Requirements:
 * 1. Development behavior:
 *    - If NEXT_PUBLIC_API_URL is configured, use it.
 *    - Otherwise, default to "http://localhost:8000" in development mode.
 * 2. Production behavior:
 *    - Never depend on localhost in production.
 *    - Default to the deployed Render backend URL:
 *      https://lenny-podcast-assistant.onrender.com
 *    - If NEXT_PUBLIC_API_URL is provided and not a loopback address, use it.
 * 3. Startup logging:
 *    - Log the resolved API base URL at startup.
 * 4. Automatic Reachability Failover:
 *    - If configured to localhost and a network request fails (e.g. local backend down),
 *      automatically fail over to the production Render URL.
 */

export const PRODUCTION_API_URL = "https://lenny-podcast-assistant.onrender.com";

export function resolveApiBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL?.trim();

  // Production environment check: never allow localhost in production builds
  if (process.env.NODE_ENV === "production") {
    if (envUrl && !envUrl.includes("localhost") && !envUrl.includes("127.0.0.1")) {
      return envUrl.replace(/\/+$/, "");
    }
    return PRODUCTION_API_URL;
  }

  // Development environment check
  if (envUrl) {
    return envUrl.replace(/\/+$/, "");
  }

  return "http://localhost:8000";
}

export const API_BASE_URL = resolveApiBaseUrl();

// Startup logging requirement: console.log("API Base URL:", API_BASE_URL);
console.log("API Base URL:", API_BASE_URL);

/**
 * Mutable active base URL allowing automatic runtime failover
 * if local backend is unreachable.
 */
let activeBaseUrl = API_BASE_URL;

export function getActiveApiBaseUrl(): string {
  return activeBaseUrl;
}

export function setActiveApiBaseUrl(url: string): void {
  activeBaseUrl = url.replace(/\/+$/, "");
  console.log("API Base URL updated to:", activeBaseUrl);
}

export function isLocalhost(url: string = activeBaseUrl): boolean {
  return url.includes("localhost") || url.includes("127.0.0.1");
}

export function failoverToProduction(reason?: string): string {
  if (activeBaseUrl !== PRODUCTION_API_URL) {
    console.warn(
      `[API Failover] Cannot reach local backend at ${activeBaseUrl}${reason ? ` (${reason})` : ""}. ` +
      `Automatically failing over to deployed backend: ${PRODUCTION_API_URL}`
    );
    activeBaseUrl = PRODUCTION_API_URL;
  }
  return activeBaseUrl;
}
