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
    ["Extreme", "#d42d41"],
    ["Severe", "#f08c11"],
    ["Moderate", "#f4cf00"],
    ["Minor", "#399cc7"],
  ])("colors %s alerts with the palette color %s", (severity, color) => {
    expect(evaluate(severityColorExpression(), severity)).toBe(color);
  });

  it("matches severities case-insensitively (CAP producers vary)", () => {
    const expression = severityColorExpression();
    expect(evaluate(expression, "SEVERE")).toBe("#f08c11");
    expect(evaluate(expression, "extreme")).toBe("#d42d41");
  });

  it("falls back to the Unknown color for unexpected/absent severities", () => {
    expect(evaluate(severityColorExpression(), "Unknown")).toBe("#82a8df");
    expect(evaluate(severityColorExpression(), "Bizarre")).toBe("#82a8df");
  });
});
