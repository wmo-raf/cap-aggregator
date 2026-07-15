import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ExplorerSidebar from "@/components/ExplorerSidebar.vue";

function mountSidebar(variant: "overlay" | "inline") {
  return mount(ExplorerSidebar, {
    props: { variant, label: "Test sidebar" },
    slots: { default: "<p data-testid='content'>sidebar content</p>" },
    global: { stubs: { transition: true } },
  });
}

describe.each(["overlay", "inline"] as const)("ExplorerSidebar (%s)", (variant) => {
  it("starts open with the slot content visible", () => {
    const wrapper = mountSidebar(variant);

    expect(wrapper.find("[data-testid='content']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='sidebar-toggle']").attributes("aria-expanded")).toBe("true");
    expect(wrapper.find("aside").attributes("aria-label")).toBe("Test sidebar");
  });

  it("collapses and reopens via the toggle", async () => {
    const wrapper = mountSidebar(variant);
    const toggle = wrapper.find("[data-testid='sidebar-toggle']");

    await toggle.trigger("click");
    expect(wrapper.find("[data-testid='content']").exists()).toBe(false);
    expect(toggle.attributes("aria-expanded")).toBe("false");

    await toggle.trigger("click");
    expect(wrapper.find("[data-testid='content']").exists()).toBe(true);
  });
});
