import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";

import ExplorerSidebar from "@/components/ExplorerSidebar.vue";
import { useSidebar } from "@/composables/useSidebar";

function mountSidebar() {
  return mount(ExplorerSidebar, {
    props: { title: "Alert archive", description: "Alerts issued within the selected date range." },
    slots: { default: "<p data-testid='content'>sidebar content</p>" },
    global: { stubs: { transition: true } },
  });
}

describe("ExplorerSidebar", () => {
  beforeEach(() => useSidebar().openSidebar());

  it("renders the header (title, description) above the slot content", () => {
    const wrapper = mountSidebar();

    expect(wrapper.find("h2").text()).toBe("Alert archive");
    expect(wrapper.text()).toContain("Alerts issued within the selected date range.");
    expect(wrapper.find("[data-testid='content']").exists()).toBe(true);
    expect(wrapper.find("aside").attributes("aria-label")).toBe("Alert archive");
  });

  it("closes via the header close button (shared state)", async () => {
    const wrapper = mountSidebar();

    await wrapper.find("[data-testid='sidebar-close']").trigger("click");

    expect(wrapper.find("aside").exists()).toBe(false);
    expect(useSidebar().open.value).toBe(false);
  });

  it("has no floating toggle of its own — reopening is the menu's job", () => {
    useSidebar().close();
    const wrapper = mountSidebar();

    expect(wrapper.find("aside").exists()).toBe(false);
    expect(wrapper.find("[data-testid='sidebar-toggle']").exists()).toBe(false);
  });
});
