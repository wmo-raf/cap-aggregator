import { describe, expect, it } from "vitest";

import { nextStep, roundToBucket, timeFromQuery, timeToQuery } from "@/lib/timeControl";

describe("time control", () => {
  it("floors timestamps to 5-minute buckets (nginx tile-cache alignment)", () => {
    const t = new Date("2026-07-15T10:03:47Z");
    expect(roundToBucket(t).toISOString()).toBe("2026-07-15T10:00:00.000Z");

    const exact = new Date("2026-07-15T10:05:00Z");
    expect(roundToBucket(exact).toISOString()).toBe("2026-07-15T10:05:00.000Z");

    const late = new Date("2026-07-15T23:59:59Z");
    expect(roundToBucket(late).toISOString()).toBe("2026-07-15T23:55:00.000Z");
  });

  it("round-trips the selected time through the URL query", () => {
    const t = new Date("2026-07-10T12:34:56Z");

    const query = timeToQuery(t);
    expect(query).toEqual({ t: "2026-07-10T12:30:00.000Z" }); // bucketed in the URL too

    expect(timeFromQuery(query)?.toISOString()).toBe("2026-07-10T12:30:00.000Z");
  });

  it("serializes live mode (no selected time) as an absent param", () => {
    expect(timeToQuery(null)).toEqual({});
    expect(timeFromQuery({})).toBeNull();
    expect(timeFromQuery({ t: "not-a-date" })).toBeNull();
  });

  it("steps time forward by the given minutes", () => {
    const t = new Date("2026-07-15T10:00:00Z");
    expect(nextStep(t, 30).toISOString()).toBe("2026-07-15T10:30:00.000Z");
  });
});
