import { describe, expect, it } from "vitest";

import { BASEMAPS, basemapStyleUrl, resolveBasemapId } from "@/lib/basemap";

describe("basemaps", () => {
  it("offers a light and a dark CARTO style", () => {
    const ids = BASEMAPS.map((b) => b.id);
    expect(ids).toContain("positron");
    expect(ids).toContain("dark-matter");
  });

  it("follows the app theme when the user has not chosen a basemap", () => {
    expect(resolveBasemapId(null, true)).toBe("dark-matter");
    expect(resolveBasemapId(null, false)).toBe("positron");
  });

  it("keeps an explicit user choice regardless of theme", () => {
    expect(resolveBasemapId("positron", true)).toBe("positron");
    expect(resolveBasemapId("dark-matter", false)).toBe("dark-matter");
  });

  it("builds keyless CARTO style URLs", () => {
    for (const { id } of BASEMAPS) {
      const url = basemapStyleUrl(id);
      expect(url).toMatch(/^https:\/\/basemaps\.cartocdn\.com\/gl\/.+\/style\.json$/);
      expect(url).not.toMatch(/key|token/i);
    }
  });
});
