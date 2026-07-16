import { describe, expect, it } from "vitest";

import { activeAt, deriveTimeButtons } from "@/lib/timeButtons";

// Local-time constructions keep these assertions timezone-independent.
const now = new Date(2026, 6, 15, 9, 0, 0); // Wed 15 July 2026, 09:00 local
const hoursFromNow = (n: number) => new Date(now.getTime() + n * 3_600_000);
const iso = (d: Date) => d.toISOString();

describe("activeAt", () => {
  it("is active when t falls inside [effective, expires)", () => {
    const window = { effective: iso(hoursFromNow(-1)), expires: iso(hoursFromNow(1)) };

    expect(activeAt(window, now)).toBe(true);
    expect(activeAt(window, hoursFromNow(2))).toBe(false);
    expect(activeAt(window, hoursFromNow(-2))).toBe(false);
  });

  it("treats a missing effective as already started, missing expires as unbounded", () => {
    expect(activeAt({ effective: "", expires: iso(hoursFromNow(1)) }, now)).toBe(true);
    expect(activeAt({ effective: iso(hoursFromNow(-1)), expires: "" }, hoursFromNow(100))).toBe(true);
  });
});

describe("deriveTimeButtons", () => {
  it("always offers Now (live view) even with no alerts", () => {
    expect(deriveTimeButtons([], now)).toEqual([{ key: "now", label: "Now", t: null }]);
  });

  it("offers +24h only when something is active at that instant", () => {
    const longRunning = { effective: iso(hoursFromNow(20)), expires: iso(hoursFromNow(30)) };
    const expiresSoon = { effective: iso(hoursFromNow(1)), expires: iso(hoursFromNow(2)) };

    expect(deriveTimeButtons([expiresSoon], now).map((b) => b.key)).toEqual(["now"]);

    const buttons = deriveTimeButtons([longRunning], now);
    expect(buttons.map((b) => b.key)).toEqual(["now", "24h"]);
    expect(buttons[1].label).toBe("+24h");
    expect(buttons[1].t!.getTime()).toBe(hoursFromNow(24).getTime());
  });

  it("offers weekday buttons at local noon for days 2-7 that have activity", () => {
    const fridayStorm = {
      effective: iso(new Date(2026, 6, 17, 10)),
      expires: iso(new Date(2026, 6, 17, 18)),
    };

    const buttons = deriveTimeButtons([fridayStorm], now, "en-GB");

    const dayButtons = buttons.filter((b) => b.key.startsWith("day-"));
    expect(dayButtons).toHaveLength(1); // quiet days get no button
    expect(dayButtons[0].label).toBe("Fri");
    expect(dayButtons[0].t!.getTime()).toBe(new Date(2026, 6, 17, 12).getTime());
  });

  it("offers Future jumping to the first alert starting beyond 7 days", () => {
    const far = { effective: iso(new Date(2026, 6, 25, 6)), expires: iso(new Date(2026, 6, 26, 6)) };
    const farther = { effective: iso(new Date(2026, 6, 28, 6)), expires: "" };

    const buttons = deriveTimeButtons([farther, far], now);

    const future = buttons.find((b) => b.key === "future")!;
    expect(future.label).toBe("Future");
    expect(future.t!.getTime()).toBe(new Date(2026, 6, 25, 6).getTime());
  });

  it("omits Future when everything starts within the week", () => {
    const nearby = { effective: iso(hoursFromNow(30)), expires: iso(hoursFromNow(40)) };

    expect(deriveTimeButtons([nearby], now).some((b) => b.key === "future")).toBe(false);
  });
});
