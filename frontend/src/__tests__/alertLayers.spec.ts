import { describe, expect, it } from "vitest";

import { ALERTS_SOURCE_ID, alertLayers } from "@/lib/alertLayers";
import { severityColorExpression } from "@/lib/severity";

describe("alertLayers", () => {
  const layers = alertLayers();

  it("styles alert polygons from the severity of each feature", () => {
    const fill = layers.find((l) => l.type === "fill");
    expect(fill).toBeDefined();
    expect(fill!.source).toBe(ALERTS_SOURCE_ID);
    expect(fill!["source-layer"]).toBe("alerts");
    expect(fill!.paint).toMatchObject({ "fill-color": severityColorExpression() });
  });

  it("outlines polygons so adjacent alerts of one severity stay distinguishable", () => {
    const line = layers.find((l) => l.type === "line");
    expect(line).toBeDefined();
    expect(line!["source-layer"]).toBe("alerts");
  });

  it("marks centroids for low-zoom visibility, colored by severity", () => {
    const circle = layers.find((l) => l.type === "circle");
    expect(circle).toBeDefined();
    expect(circle!["source-layer"]).toBe("alert_centroids");
    expect(circle!.paint).toMatchObject({ "circle-color": severityColorExpression() });
    expect(circle!.maxzoom).toBeGreaterThan(0);
  });

  it("gives every layer a unique id (MapLibre rejects duplicates)", () => {
    const ids = layers.map((l) => l.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
