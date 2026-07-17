import { describe, expect, it } from "vitest";

import {
  emptyFilters,
  filtersFromRouteQuery,
  filtersToRouteQuery,
  hasActiveFilters,
  searchParamsFromFilters,
  tileQueryFromFilters,
} from "@/lib/filters";

describe("alert filters", () => {
  it("starts empty and inactive", () => {
    expect(hasActiveFilters(emptyFilters())).toBe(false);
  });

  it("round-trips through URL route query params", () => {
    const filters = {
      ...emptyFilters(),
      severity: ["Severe", "Extreme"],
      category: ["Met"],
      msgType: ["Alert"],
      country: ["ke", "dz"],
    };

    const query = filtersToRouteQuery(filters);
    expect(query).toEqual({
      severity: "Severe,Extreme",
      category: "Met",
      msg_type: "Alert",
      country: "ke,dz",
    });
    expect(filtersFromRouteQuery(query)).toEqual(filters);
  });

  it("omits empty facets from the URL entirely", () => {
    expect(filtersToRouteQuery(emptyFilters())).toEqual({});
  });

  it("tolerates repeated params and unknown keys when parsing", () => {
    const parsed = filtersFromRouteQuery({
      severity: ["Severe", "Minor"], // vue-router gives arrays for repeated params
      urgency: "Immediate",
      unknown: "ignored",
    });

    expect(parsed.severity).toEqual(["Severe", "Minor"]);
    expect(parsed.urgency).toEqual(["Immediate"]);
    expect(hasActiveFilters(parsed)).toBe(true);
  });

  it("maps filters to Martin tile query params (CSV, empty facets omitted)", () => {
    const filters = { ...emptyFilters(), severity: ["Severe"], country: ["ke"] };

    expect(tileQueryFromFilters(filters)).toEqual({ status: "Actual", severity: "Severe", country: "ke" });
  });

  it("always pins the tile query to Actual status — the map must match the search API's public default", () => {
    expect(tileQueryFromFilters(emptyFilters())).toEqual({ status: "Actual" });
  });

  it("builds /api/search/ params from filters plus the viewport bbox", () => {
    const filters = { ...emptyFilters(), severity: ["Severe", "Extreme"], urgency: ["Immediate"] };
    const params = searchParamsFromFilters(filters, [-10.5, -5, 42.25, 38]);

    expect(params.get("severity")).toBe("Severe,Extreme");
    expect(params.get("urgency")).toBe("Immediate");
    expect(params.get("bbox")).toBe("-10.5,-5,42.25,38");
    expect(params.get("category")).toBeNull();
  });

  it("builds search params without a bbox when none is given", () => {
    const params = searchParamsFromFilters(emptyFilters(), null);

    expect(params.get("bbox")).toBeNull();
  });

  it("carries the selected time so the list time-travels with the map", () => {
    const t = new Date("2026-07-10T12:30:00Z");

    const params = searchParamsFromFilters(emptyFilters(), null, t);
    expect(params.get("t")).toBe("2026-07-10T12:30:00.000Z");

    expect(searchParamsFromFilters(emptyFilters(), null, null).get("t")).toBeNull();
  });
});
