import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { basemapStyleUrl, resolveBasemapId } from "@/lib/basemap";
import { SEVERITIES, SEVERITY_FALLBACK_COLOR } from "@/lib/severity";

// Progressive enhancement for the alert detail page: renders the alert area
// (from the #capagg-area-geojson json_script) on a small basemap. The page is
// complete without this — the map is purely additive.

type Position = number[];

function collectPositions(coordinates: unknown, out: Position[]): void {
  if (!Array.isArray(coordinates)) return;
  if (typeof coordinates[0] === "number") {
    out.push(coordinates as Position);
    return;
  }
  for (const child of coordinates) collectPositions(child, out);
}

function geometryBounds(geometry: { coordinates: unknown }): maplibregl.LngLatBounds | null {
  const positions: Position[] = [];
  collectPositions(geometry.coordinates, positions);
  if (!positions.length) return null;
  const bounds = new maplibregl.LngLatBounds();
  for (const [lng, lat] of positions) bounds.extend([lng, lat]);
  return bounds;
}

document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("capagg-area-map");
  const payload = document.getElementById("capagg-area-geojson");
  if (!container || !payload?.textContent) return;

  const geometry = JSON.parse(payload.textContent) as { type: string; coordinates: unknown };
  const severity = container.dataset.severity ?? "";
  const color = SEVERITIES.find((s) => s.value === severity)?.color ?? SEVERITY_FALLBACK_COLOR;
  const isDark = () => document.documentElement.classList.contains("dark");

  const map = new maplibregl.Map({
    container,
    style: basemapStyleUrl(resolveBasemapId(null, isDark())),
    center: [0, 0],
    zoom: 1,
    scrollZoom: false,
    attributionControl: { compact: true },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

  map.on("style.load", () => {
    map.addSource("alert-area", { type: "geojson", data: { type: "Feature", geometry, properties: {} } });
    map.addLayer({
      id: "alert-area-fill",
      type: "fill",
      source: "alert-area",
      paint: { "fill-color": color, "fill-opacity": 0.35 },
    });
    map.addLayer({
      id: "alert-area-outline",
      type: "line",
      source: "alert-area",
      paint: { "line-color": color, "line-width": 2 },
    });
  });

  const bounds = geometryBounds(geometry);
  if (bounds) map.fitBounds(bounds, { padding: 32, maxZoom: 9, duration: 0 });

  // Follow the header theme toggle without a reload (style.load re-adds layers)
  new MutationObserver(() => {
    map.setStyle(basemapStyleUrl(resolveBasemapId(null, isDark())));
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
});
