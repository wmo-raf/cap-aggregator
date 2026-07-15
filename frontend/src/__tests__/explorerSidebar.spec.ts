import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import ExplorerSidebar from "@/components/ExplorerSidebar.vue";
import { useSidebar } from "@/composables/useSidebar";
import { routes } from "@/router";

async function mountSidebar() {
  const router = createRouter({ history: createMemoryHistory("/explorer/"), routes });
  await router.push("/table");
  await router.isReady();
  return mount(ExplorerSidebar, {
    props: { title: "Alert archive", description: "Alerts issued within the selected date range." },
    slots: { default: "<p data-testid='content'>sidebar content</p>" },
    global: { plugins: [router], stubs: { transition: true } },
  });
}

describe("ExplorerSidebar", () => {
  beforeEach(() => useSidebar().open("table"));

  it("renders the header (title, description) above the slot content", async () => {
    const wrapper = await mountSidebar();

    expect(wrapper.find("h2").text()).toBe("Alert archive");
    expect(wrapper.text()).toContain("Alerts issued within the selected date range.");
    expect(wrapper.find("[data-testid='content']").exists()).toBe(true);
    expect(wrapper.find("aside").attributes("aria-label")).toBe("Alert archive");
  });

  it("closes its own view's state via the header close button", async () => {
    const wrapper = await mountSidebar();

    await wrapper.find("[data-testid='sidebar-close']").trigger("click");

    expect(wrapper.find("aside").exists()).toBe(false);
    expect(useSidebar().isOpen("table").value).toBe(false);
    expect(useSidebar().isOpen("map").value).toBe(true); // other views untouched
  });

  it("has no floating toggle of its own — reopening is the menu's job", async () => {
    useSidebar().close("table");
    const wrapper = await mountSidebar();

    expect(wrapper.find("aside").exists()).toBe(false);
    expect(wrapper.find("[data-testid='sidebar-toggle']").exists()).toBe(false);
  });
});
