import { describe, expect, it } from "vitest";

import { buildPopupContent, dedupeAlertFeatures } from "@/lib/popup";

const feature = (id: number, over: Record<string, unknown> = {}) => ({
  properties: {
    id,
    chain: id * 10,
    event: "Flood Warning",
    headline: `Alert ${id}`,
    severity: "Moderate",
    authority: "kenya-met",
    expires: "2026-07-16T00:00:00Z",
    ...over,
  },
});

describe("map popup", () => {
  it("dedupes features (a polygon can span tile borders) and ranks worst first", () => {
    const alerts = dedupeAlertFeatures([
      feature(1, { severity: "Minor" }),
      feature(2, { severity: "Extreme" }),
      feature(1, { severity: "Minor" }),
      feature(3, { severity: "Severe" }),
    ]);

    expect(alerts.map((a) => a.id)).toEqual([2, 3, 1]);
  });

  it("renders every overlapping alert with a detail link", () => {
    const content = buildPopupContent(
      dedupeAlertFeatures([feature(1), feature(2, { severity: "Severe", headline: "" })]),
    );

    const links = [...content.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(links).toEqual(["/alerts/20/", "/alerts/10/"]);
    expect(content.textContent).toContain("Alert 1");
    expect(content.textContent).toContain("Flood Warning"); // falls back to event when headline empty
    expect(content.textContent).toContain("kenya-met");
  });
});
