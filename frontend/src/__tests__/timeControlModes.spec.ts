import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import TimeControl from "@/components/TimeControl.vue";

const HOUR = 3_600_000;
const iso = (msFromNow: number) => new Date(Date.now() + msFromNow).toISOString();

// one alert active now that is still active at now+24h → chips: Now, +24h
const WINDOWS = [{ effective: iso(-2 * HOUR), expires: iso(30 * HOUR) }];

function mountControl(modelValue: Date | null = null, windows = WINDOWS) {
  return mount(TimeControl, { props: { modelValue, windows } });
}

describe("TimeControl modes", () => {
  it("defaults to Live mode with data-driven chips, Now selected, no picker", () => {
    const wrapper = mountControl();

    expect(wrapper.find('[data-testid="time-mode-live"]').attributes("aria-pressed")).toBe("true");
    const chips = wrapper.findAll("[data-time-button]");
    expect(chips.map((c) => c.text())).toEqual(["Now", "+24h"]);
    expect(chips[0].attributes("aria-pressed")).toBe("true");
    expect(wrapper.find('input[type="datetime-local"]').exists()).toBe(false);
  });

  it("emits the chip instant on click, and null (live) for Now", async () => {
    const wrapper = mountControl();
    const chips = wrapper.findAll("[data-time-button]");

    await chips[1].trigger("click"); // +24h
    const emitted = wrapper.emitted("update:modelValue")!;
    const t = emitted[0][0] as Date;
    expect(Math.abs(t.getTime() - (Date.now() + 24 * HOUR))).toBeLessThan(10 * 60 * 1000);

    await chips[0].trigger("click"); // Now
    expect(emitted[1]).toEqual([null]);
  });

  it("highlights the chip matching a future t (bucket-tolerant)", () => {
    const wrapper = mountControl(new Date(Date.now() + 24 * HOUR));

    const chips = wrapper.findAll("[data-time-button]");
    expect(chips[1].attributes("aria-pressed")).toBe("true");
    expect(chips[0].attributes("aria-pressed")).toBe("false");
  });

  it("switches to Historical without emitting: past-capped picker plus play button", async () => {
    const wrapper = mountControl();

    await wrapper.find('[data-testid="time-mode-historical"]').trigger("click");

    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    const input = wrapper.find('input[type="datetime-local"]');
    expect(input.exists()).toBe(true);
    expect(input.attributes("max")).toBeTruthy(); // past instants only
    expect(wrapper.find('[data-testid="play-toggle"]').exists()).toBe(true);
    expect(wrapper.findAll("[data-time-button]")).toHaveLength(0);
  });

  it("opens in Historical mode when t is in the past", () => {
    const wrapper = mountControl(new Date(Date.now() - 24 * HOUR));

    expect(wrapper.find('[data-testid="time-mode-historical"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.find('input[type="datetime-local"]').exists()).toBe(true);
  });
});
