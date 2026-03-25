/**
 * API base: dev 走 Vite 代理 /minigame-tracker/api → /api；
 * 生产用绝对 URL，避免 new URL("/minigame-tracker/api/...") 单参在浏览器里不合法。
 */
export function apiUrl(path: string): string {
  const base = import.meta.env.BASE_URL;
  const b = base.endsWith("/") ? base : `${base}/`;
  const p = path.startsWith("/") ? path.slice(1) : path;
  const relative = `${b}api/${p}`;
  if (typeof window !== "undefined" && window.location?.origin) {
    return new URL(relative, window.location.origin).href;
  }
  return relative;
}
