export interface AppConfig {
  /** Base URL for the Martin tile server (no trailing slash). */
  tilesBase: string;
}

const DEFAULTS: AppConfig = {
  // nginx proxies /martin/ to the Martin container in the compose stack
  tilesBase: "/martin",
};

/**
 * Runtime config injected by the Django shell as a JSON <script id="capagg-config">
 * (Django's json_script). Falls back to production defaults so the SPA still
 * works if the shell omits it.
 */
export function appConfig(): AppConfig {
  const element = document.getElementById("capagg-config");
  if (!element?.textContent) return { ...DEFAULTS };
  try {
    const parsed = JSON.parse(element.textContent) as Partial<AppConfig>;
    const tilesBase = (parsed.tilesBase ?? DEFAULTS.tilesBase).replace(/\/+$/, "");
    return { tilesBase };
  } catch {
    return { ...DEFAULTS };
  }
}

/** MapLibre raster/vector tile URL template for the Martin `alerts` function source. */
export function alertTileUrlTemplate(): string {
  return `${appConfig().tilesBase}/alerts/{z}/{x}/{y}`;
}
