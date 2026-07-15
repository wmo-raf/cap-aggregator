export interface AppConfig {
  /** Base URL for the Martin tile server (no trailing slash). */
  tilesBase: string;
}

const DEFAULTS: AppConfig = {
  // nginx proxies /martin/ to the Martin container in the compose stack
  tilesBase: "/martin",
};

/** MapLibre fetches tiles in a worker spawned from a blob: URL, which has no
 * base to resolve relative URLs against ("Failed to parse URL from /martin/…")
 * — so a site-relative base must become absolute here in the page context. */
function absolute(base: string): string {
  return base.startsWith("/") ? `${window.location.origin}${base}` : base;
}

/**
 * Runtime config injected by the Django shell as a JSON <script id="capagg-config">
 * (Django's json_script). Falls back to production defaults so the SPA still
 * works if the shell omits it.
 */
export function appConfig(): AppConfig {
  const element = document.getElementById("capagg-config");
  let tilesBase = DEFAULTS.tilesBase;
  if (element?.textContent) {
    try {
      const parsed = JSON.parse(element.textContent) as Partial<AppConfig>;
      tilesBase = parsed.tilesBase ?? DEFAULTS.tilesBase;
    } catch {
      // fall through to the default
    }
  }
  return { tilesBase: absolute(tilesBase.replace(/\/+$/, "")) };
}

/** MapLibre raster/vector tile URL template for the Martin `alerts` function source. */
export function alertTileUrlTemplate(): string {
  return `${appConfig().tilesBase}/alerts/{z}/{x}/{y}`;
}
