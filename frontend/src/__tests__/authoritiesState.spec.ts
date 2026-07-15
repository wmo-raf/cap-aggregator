import { describe, expect, it } from "vitest";

import { groupByCountry, stateFromQuery, stateToQuery } from "@/lib/authoritiesState";

const AUTHORITY = (over: Record<string, unknown>) => ({
  name: "X",
  slug: "x",
  country: "KE",
  country_name: "Kenya",
  website: "",
  active_alert_count: 0,
  ...over,
});

describe("authorities sidebar state", () => {
  it("defaults to flat + all authorities", () => {
    expect(stateFromQuery({})).toEqual({ activeOnly: false, group: "flat" });
  });

  it("round-trips through the URL query, omitting defaults", () => {
    const state = { activeOnly: true, group: "country" as const };

    const query = stateToQuery(state);
    expect(query).toEqual({ active: "1", group: "country" });
    expect(stateFromQuery(query)).toEqual(state);

    expect(stateToQuery({ activeOnly: false, group: "flat" })).toEqual({});
  });

  it("ignores malformed query values", () => {
    expect(stateFromQuery({ active: "banana", group: "sideways" })).toEqual({
      activeOnly: false,
      group: "flat",
    });
  });

  it("groups authorities by country, sorted by country name", () => {
    const groups = groupByCountry([
      AUTHORITY({ slug: "ke-1", country: "KE", country_name: "Kenya" }),
      AUTHORITY({ slug: "dz-1", country: "DZ", country_name: "Algeria" }),
      AUTHORITY({ slug: "ke-2", country: "KE", country_name: "Kenya" }),
    ]);

    expect(groups.map((g) => g.name)).toEqual(["Algeria", "Kenya"]);
    expect(groups[1].items.map((a) => a.slug)).toEqual(["ke-1", "ke-2"]);
    expect(groups[0].code).toBe("DZ");
  });
});
