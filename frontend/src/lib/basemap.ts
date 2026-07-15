export type BasemapId = "positron" | "dark-matter";

/** Free CARTO vector styles — no API key; attribution comes with the style. */
export const BASEMAPS: { id: BasemapId; label: string; style: string }[] = [
  { id: "positron", label: "Light", style: "positron-gl-style" },
  { id: "dark-matter", label: "Dark", style: "dark-matter-gl-style" },
];

export function basemapStyleUrl(id: BasemapId): string {
  const basemap = BASEMAPS.find((b) => b.id === id) ?? BASEMAPS[0];
  return `https://basemaps.cartocdn.com/gl/${basemap.style}/style.json`;
}

/** The basemap follows the app theme unless the user explicitly picked one. */
export function resolveBasemapId(manual: BasemapId | null, isDark: boolean): BasemapId {
  return manual ?? (isDark ? "dark-matter" : "positron");
}
