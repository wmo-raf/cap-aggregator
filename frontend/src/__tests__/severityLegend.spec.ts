import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import SeverityLegend from "@/components/SeverityLegend.vue";
import { SEVERITIES } from "@/lib/severity";

/** jsdom normalizes hex colors to rgb() in style attributes. */
function hexToRgb(hex: string): string {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return `rgb(${r}, ${g}, ${b})`;
}

describe("SeverityLegend", () => {
  it("shows one labelled swatch per severity, worst first", () => {
    const wrapper = mount(SeverityLegend);
    const items = wrapper.findAll("[data-severity]");

    expect(items).toHaveLength(SEVERITIES.length);
    SEVERITIES.forEach((severity, index) => {
      expect(items[index].attributes("data-severity")).toBe(severity.value);
      expect(items[index].text()).toContain(severity.label);
      expect(items[index].find(".legend-swatch").attributes("style")).toContain(hexToRgb(severity.color));
    });
  });
});
