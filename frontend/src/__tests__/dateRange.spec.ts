import { describe, expect, it } from "vitest";

import {
  DATE_PRESETS,
  defaultRange,
  formatDateRange,
  matchPreset,
  presetRange,
  rangeFromQuery,
  rangeToQuery,
  tableSearchParams,
} from "@/lib/dateRange";
import { emptyFilters } from "@/lib/filters";

describe("table date range", () => {
  const now = new Date("2026-07-15T10:00:00Z");

  it("defaults to the last 7 days inclusive of today", () => {
    expect(defaultRange(now)).toEqual({ from: "2026-07-08", to: "2026-07-15" });
  });

  it("round-trips through the URL query", () => {
    const range = { from: "2026-06-01", to: "2026-06-30" };

    const query = rangeToQuery(range);
    expect(query).toEqual({ from: "2026-06-01", to: "2026-06-30" });
    expect(rangeFromQuery(query, now)).toEqual(range);
  });

  it("falls back to the default range for missing or malformed params", () => {
    expect(rangeFromQuery({}, now)).toEqual(defaultRange(now));
    expect(rangeFromQuery({ from: "garbage", to: "2026-06-30" }, now)).toEqual(defaultRange(now));
  });

  it("builds table search params: range + facets + pagination", () => {
    const params = tableSearchParams(
      { ...emptyFilters(), severity: ["Severe"] },
      { from: "2026-06-01", to: "2026-06-30" },
      50,
    );

    expect(params.get("effective_from")).toBe("2026-06-01");
    expect(params.get("effective_to")).toBe("2026-06-30");
    expect(params.get("severity")).toBe("Severe");
    expect(params.get("limit")).toBe("50");
    expect(params.get("offset")).toBe("50");
  });

  it("offers the common presets, resolving each to an absolute range", () => {
    expect(DATE_PRESETS.map((p) => p.key)).toEqual(["today", "7d", "30d", "90d"]);
    expect(presetRange("today", now)).toEqual({ from: "2026-07-15", to: "2026-07-15" });
    expect(presetRange("7d", now)).toEqual(defaultRange(now)); // the default IS last 7 days
    expect(presetRange("30d", now)).toEqual({ from: "2026-06-15", to: "2026-07-15" });
    expect(presetRange("90d", now)).toEqual({ from: "2026-04-16", to: "2026-07-15" });
  });

  it("derives the matching preset from an absolute range, or null for custom ranges", () => {
    expect(matchPreset(defaultRange(now), now)).toBe("7d");
    expect(matchPreset({ from: "2026-07-15", to: "2026-07-15" }, now)).toBe("today");
    expect(matchPreset({ from: "2026-06-01", to: "2026-06-30" }, now)).toBeNull();
  });

  it("formats the applied range compactly for the header", () => {
    const label = formatDateRange({ from: "2026-07-09", to: "2026-07-16" }, "en-GB");

    expect(label).toContain("9");
    expect(label).toContain("16");
    expect(label).toContain("Jul 2026");
  });

  it("collapses a single-day range to one date", () => {
    expect(formatDateRange({ from: "2026-07-16", to: "2026-07-16" }, "en-GB")).toBe("16 Jul 2026");
  });

  it("shows both years when the range crosses years", () => {
    const label = formatDateRange({ from: "2025-12-20", to: "2026-01-05" }, "en-GB");

    expect(label).toContain("2025");
    expect(label).toContain("2026");
  });

  it("orders by the active grouping so grouped rows stay contiguous across pages", () => {
    const range = { from: "2026-06-01", to: "2026-06-30" };

    // the default (effective) grouping rides the API's newest-first default
    expect(tableSearchParams(emptyFilters(), range, 0).get("order")).toBeNull();
    expect(tableSearchParams(emptyFilters(), range, 0, "effective").get("order")).toBeNull();
    expect(tableSearchParams(emptyFilters(), range, 0, "country").get("order")).toBe("country");
    expect(tableSearchParams(emptyFilters(), range, 0, "severity").get("order")).toBe("severity");
  });
});
