import { describe, expect, it } from "vitest";

import { severityColorExpression } from "@/lib/severity";

/** Evaluate a MapLibre ["match", ["downcase", ["get","severity"]], ...] expression by hand. */
function evaluate(expression: unknown[], severity: string): string {
  const [op, , ...rest] = expression as [string, unknown, ...string[]];
  expect(op).toBe("match");
  const fallback = rest[rest.length - 1] as string;
  for (let i = 0; i < rest.length - 1; i += 2) {
    if (rest[i] === severity.toLowerCase()) return rest[i + 1] as string;
  }
  return fallback;
}

describe("severityColorExpression", () => {
  it.each([
    ["Extreme", "#7a0177"],
    ["Severe", "#e31a1c"],
    ["Moderate", "#fd8d3c"],
    ["Minor", "#fecc5c"],
  ])("colors %s alerts with the MeteoAlarm color %s", (severity, color) => {
    expect(evaluate(severityColorExpression(), severity)).toBe(color);
  });

  it("matches severities case-insensitively (CAP producers vary)", () => {
    const expression = severityColorExpression();
    expect(evaluate(expression, "SEVERE")).toBe("#e31a1c");
    expect(evaluate(expression, "extreme")).toBe("#7a0177");
  });

  it("falls back to a neutral color for Unknown/absent severities", () => {
    const fallback = evaluate(severityColorExpression(), "Unknown");
    expect(fallback).toMatch(/^#[0-9a-f]{6}$/i);
    const meteoalarm = ["#7a0177", "#e31a1c", "#fd8d3c", "#fecc5c"];
    expect(meteoalarm).not.toContain(fallback.toLowerCase());
  });
});
