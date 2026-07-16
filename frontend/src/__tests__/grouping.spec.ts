import { describe, expect, it } from "vitest";

import {
  groupByCountryAuthority,
  groupByEffectiveDay,
  groupBySeverity,
  groupingFromQuery,
  groupingToQuery,
} from "@/lib/grouping";
import { SEVERITY_FALLBACK_COLOR } from "@/lib/severity";

const alert = (severity: string, id: number) => ({ severity, id });

describe("groupBySeverity", () => {
  it("groups worst-first and omits empty severities", () => {
    const groups = groupBySeverity([
      alert("Minor", 1),
      alert("Extreme", 2),
      alert("Minor", 3),
      alert("Severe", 4),
    ]);

    expect(groups.map((g) => g.label)).toEqual(["Extreme", "Severe", "Minor"]); // no Moderate group
    expect(groups[0].items.map((i) => i.id)).toEqual([2]);
    expect(groups[2].items.map((i) => i.id)).toEqual([1, 3]); // input order preserved
  });

  it("matches severities case-insensitively", () => {
    const groups = groupBySeverity([alert("SEVERE", 1), alert("severe", 2)]);

    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("Severe");
    expect(groups[0].items).toHaveLength(2);
  });

  it("keeps unexpected severities visible as trailing groups with a neutral color", () => {
    const groups = groupBySeverity([alert("Bizarre", 1), alert("Extreme", 2), alert("Unknown", 3)]);

    expect(groups.map((g) => g.label)).toEqual(["Extreme", "Bizarre", "Unknown"]);
    expect(groups[1].color).toBe(SEVERITY_FALLBACK_COLOR);
  });

  it("returns no groups for no items", () => {
    expect(groupBySeverity([])).toEqual([]);
  });
});

describe("groupByCountryAuthority", () => {
  const row = (id: number, country: string, countryName: string, slug: string, name: string) => ({
    id,
    authority: slug,
    authority_name: name,
    authority_country: country,
    authority_country_name: countryName,
  });

  it("nests authorities under their country, preserving server order", () => {
    const groups = groupByCountryAuthority([
      row(1, "KE", "Kenya", "kenya-met", "Kenya Met Department"),
      row(2, "ZA", "South Africa", "saws", "SA Weather Service"),
      row(3, "ZA", "South Africa", "saws", "SA Weather Service"),
      row(4, "ZA", "South Africa", "za-provincial", "ZA Provincial Service"),
    ]);

    expect(groups.map((g) => [g.code, g.name])).toEqual([
      ["KE", "Kenya"],
      ["ZA", "South Africa"],
    ]);
    expect(groups[1].authorities.map((a) => a.name)).toEqual([
      "SA Weather Service",
      "ZA Provincial Service",
    ]);
    expect(groups[1].authorities[0].items.map((i) => i.id)).toEqual([2, 3]);
  });

  it("keys authority groups so slugs stay unique across countries", () => {
    const groups = groupByCountryAuthority([
      row(1, "KE", "Kenya", "met", "Kenya Met"),
      row(2, "UG", "Uganda", "met", "Uganda Met"),
    ]);

    const keys = groups.flatMap((g) => g.authorities.map((a) => a.key));
    expect(new Set(keys).size).toBe(2);
  });

  it("returns no groups for no items", () => {
    expect(groupByCountryAuthority([])).toEqual([]);
  });
});

describe("groupByEffectiveDay", () => {
  const row = (id: number, effective: string | null) => ({ id, effective });

  const utc = { locale: "en-GB", timeZone: "UTC" };

  it("buckets by calendar day in the given zone, preserving newest-first server order", () => {
    const groups = groupByEffectiveDay(
      [
        row(1, "2026-07-16T23:00:00+02:00"), // 21:00 UTC — still 16 July
        row(2, "2026-07-16T09:00:00+02:00"),
        row(3, "2026-07-14T12:00:00+02:00"),
      ],
      utc,
    );

    expect(groups.map((g) => g.items.map((i) => i.id))).toEqual([[1, 2], [3]]);
    expect(groups[0].label).toBe("16 July 2026");
    expect(groups[1].label).toBe("14 July 2026");
    expect(groups[0].value).not.toBe(groups[1].value);
  });

  it("splits days by the zone's midnight, not UTC's", () => {
    const groups = groupByEffectiveDay(
      [row(1, "2026-07-16T22:30:00Z"), row(2, "2026-07-16T09:00:00Z")],
      { locale: "en-GB", timeZone: "Africa/Nairobi" }, // 22:30Z = 01:30 on 17 July
    );

    expect(groups.map((g) => g.label)).toEqual(["17 July 2026", "16 July 2026"]);
  });

  it("keeps alerts without an effective time visible in a trailing group", () => {
    const groups = groupByEffectiveDay([row(1, "2026-07-16T09:00:00Z"), row(2, null)], utc);

    expect(groups).toHaveLength(2);
    expect(groups[1].label).toBe("Unknown");
    expect(groups[1].items.map((i) => i.id)).toEqual([2]);
  });

  it("returns no groups for no items", () => {
    expect(groupByEffectiveDay([])).toEqual([]);
  });
});

describe("table grouping URL param", () => {
  it("defaults to effective-time grouping when the param is absent or unknown", () => {
    expect(groupingFromQuery({})).toBe("effective");
    expect(groupingFromQuery({ group: "bizarre" })).toBe("effective");
    expect(groupingFromQuery({ group: ["severity", "country"] })).toBe("effective");
  });

  it("accepts the country and severity groupings", () => {
    expect(groupingFromQuery({ group: "country" })).toBe("country");
    expect(groupingFromQuery({ group: "severity" })).toBe("severity");
  });

  it("round-trips through the URL query, omitting the default", () => {
    expect(groupingToQuery("effective")).toEqual({});
    expect(groupingToQuery("severity")).toEqual({ group: "severity" });
    expect(groupingFromQuery(groupingToQuery("country"))).toBe("country");
  });
});
