import { apiUrl } from "./config";

/** Rankings API may return `/api/media/{sha}`; map to SPA-aware absolute URL. */
export function resolveIconSrc(url: string | null | undefined): string {
  if (!url) return "";
  if (url.startsWith("/api/")) {
    return apiUrl(url.slice("/api/".length));
  }
  return url;
}
