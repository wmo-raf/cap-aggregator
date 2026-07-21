import { describe, expect, it, vi } from "vitest";

import { nextStep, roundToBucket, tileTime, timeFromQuery, timeToQuery, watchBucket } from "@/lib/timeControl";

describe("time control", () => {
  it("floors timestamps to 1-minute buckets (nginx tile-cache alignment)", () => {
    const t = new Date("2026-07-15T10:03:47Z");
    expect(roundToBucket(t).toISOString()).toBe("2026-07-15T10:03:00.000Z");

    const exact = new Date("2026-07-15T10:05:00Z");
    expect(roundToBucket(exact).toISOString()).toBe("2026-07-15T10:05:00.000Z");

    const late = new Date("2026-07-15T23:59:59Z");
    expect(roundToBucket(late).toISOString()).toBe("2026-07-15T23:59:00.000Z");
  });

  it("round-trips the selected time through the URL query", () => {
    const t = new Date("2026-07-10T12:34:56Z");

    const query = timeToQuery(t);
    expect(query).toEqual({ t: "2026-07-10T12:34:00.000Z" }); // bucketed in the URL too

    expect(timeFromQuery(query)?.toISOString()).toBe("2026-07-10T12:34:00.000Z");
  });

  it("serializes live mode (no selected time) as an absent param", () => {
    expect(timeToQuery(null)).toEqual({});
    expect(timeFromQuery({})).toBeNull();
    expect(timeFromQuery({ t: "not-a-date" })).toBeNull();
  });

  it("gives every tile request an explicit instant, live mode included", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-15T10:07:30Z"));

    expect(tileTime(null)).toBe("2026-07-15T10:07:00.000Z"); // live = current bucket, never absent
    expect(tileTime(new Date("2026-07-10T12:34:56Z"))).toBe("2026-07-10T12:34:00.000Z");

    vi.useRealTimers();
  });

  it("notifies watchers when the bucket rolls over, so live maps re-request tiles", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-15T10:04:00Z"));
    const onRoll = vi.fn();
    const stop = watchBucket(onRoll);

    vi.advanceTimersByTime(30_000); // still 10:04:30, same bucket
    expect(onRoll).not.toHaveBeenCalled();

    vi.advanceTimersByTime(60_000); // 10:05:30 — new bucket
    expect(onRoll).toHaveBeenCalledTimes(1);

    stop();
    vi.advanceTimersByTime(10 * 60_000); // unsubscribed: no further calls
    expect(onRoll).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("steps time forward by the given minutes", () => {
    const t = new Date("2026-07-15T10:00:00Z");
    expect(nextStep(t, 30).toISOString()).toBe("2026-07-15T10:30:00.000Z");
  });
});
