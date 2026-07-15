import type { LayerSpecification } from "maplibre-gl";

import { severityColorExpression } from "@/lib/severity";

export const ALERTS_SOURCE_ID = "capagg-alerts";

/** Below this zoom, polygon fills are tiny — centroid dots keep alerts visible. */
const CENTROID_MAX_ZOOM = 4;

/**
 * Layer specs over the Martin `alerts` function source (MVT layers `alerts`
 * polygons + `alert_centroids` points), colored by the MeteoAlarm severity
 * convention. Consumed by MapView on every style (basemap) load.
 */
export function alertLayers(): LayerSpecification[] {
  const severityColor = severityColorExpression();
  return [
    {
      id: "capagg-alerts-fill",
      type: "fill",
      source: ALERTS_SOURCE_ID,
      "source-layer": "alerts",
      paint: {
        "fill-color": severityColor,
        "fill-opacity": 0.45,
      },
    },
    {
      id: "capagg-alerts-outline",
      type: "line",
      source: ALERTS_SOURCE_ID,
      "source-layer": "alerts",
      paint: {
        "line-color": severityColor,
        "line-width": 1,
        "line-opacity": 0.9,
      },
    },
    {
      id: "capagg-alerts-centroids",
      type: "circle",
      source: ALERTS_SOURCE_ID,
      "source-layer": "alert_centroids",
      maxzoom: CENTROID_MAX_ZOOM,
      paint: {
        "circle-color": severityColor,
        "circle-radius": 4,
        "circle-stroke-width": 1,
        "circle-stroke-color": "#ffffff",
        "circle-opacity": 0.9,
      },
    },
  ];
}
