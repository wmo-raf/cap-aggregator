import { describe, expect, it } from "vitest";

import { groupBySeverity } from "@/lib/grouping";
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
