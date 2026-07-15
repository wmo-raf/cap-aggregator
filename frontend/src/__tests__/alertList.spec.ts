import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchAlertList } from "@/lib/api";
import { emptyFilters } from "@/lib/filters";

const PAGE = {
  count: 2,
  next: null,
  results: {
    type: "FeatureCollection",
    features: [
      {
        id: 7,
        geometry: { type: "Point", coordinates: [3, 28] },
        properties: {
          chain: 1396,
          event: "Sandstorm",
          headline: "Sandstorm warning",
          severity: "Moderate",
          authority: "algeria",
          expires: "2026-07-15T21:00:00Z",
          is_cancelled: false,
        },
      },
      {
        id: 9,
        geometry: null,
        properties: {
          chain: 20,
          event: "Flood",
          headline: "",
          severity: "Severe",
          authority: "kenya-met",
          expires: "2026-07-16T00:00:00Z",
          is_cancelled: false,
        },
      },
    ],
  },
};

afterEach(() => vi.unstubAllGlobals());

describe("fetchAlertList", () => {
  it("queries /api/search/ with filters + bbox and flattens GeoJSON features", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(PAGE) });
    vi.stubGlobal("fetch", fetchMock);

    const { alerts, total } = await fetchAlertList(
      { ...emptyFilters(), severity: ["Severe"] },
      [-10, -5, 42, 38],
    );

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/api/search/?");
    expect(url).toContain("severity=Severe");
    expect(url).toContain("bbox=-10%2C-5%2C42%2C38");
    expect(total).toBe(2);
    expect(alerts).toEqual([
      expect.objectContaining({ id: 7, chain: 1396, event: "Sandstorm", severity: "Moderate", authority: "algeria" }),
      expect.objectContaining({ id: 9, event: "Flood", severity: "Severe" }),
    ]);
  });

  it("throws on a failed response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    await expect(fetchAlertList(emptyFilters(), null)).rejects.toThrow();
  });
});
