import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import SideMenu from "@/components/SideMenu.vue";
import { routes } from "@/router";

async function mountMenu() {
  const router = createRouter({ history: createMemoryHistory("/explorer/"), routes });
  await router.push("/map");
  await router.isReady();
  return mount(SideMenu, { global: { plugins: [router] } });
}

describe("SideMenu", () => {
  it("shows the four labelled menu items", async () => {
    const wrapper = await mountMenu();
    const text = wrapper.text();
    for (const label of ["Map", "Table", "Authorities", "Notify"]) {
      expect(text).toContain(label);
    }
  });

  it("links the logo to the site root", async () => {
    const wrapper = await mountMenu();
    const logoLink = wrapper.find('a[href="/"]');
    expect(logoLink.exists()).toBe(true);
    expect(logoLink.find("img").attributes("alt")).toBe("CAP Aggregator");
  });

  it("has a theme toggle", async () => {
    const wrapper = await mountMenu();
    expect(wrapper.find('[data-testid="theme-toggle"]').exists()).toBe(true);
  });

  it("toggles the sidebar when the active view's item is clicked", async () => {
    const { useSidebar } = await import("@/composables/useSidebar");
    useSidebar().openSidebar();
    const wrapper = await mountMenu(); // mounted at /map

    await wrapper.find('a[href="/explorer/map"]').trigger("click");
    expect(useSidebar().open.value).toBe(false);

    await wrapper.find('a[href="/explorer/map"]').trigger("click");
    expect(useSidebar().open.value).toBe(true);
  });

  it("leaves the sidebar state alone when navigating to another view", async () => {
    const { useSidebar } = await import("@/composables/useSidebar");
    useSidebar().close();
    const wrapper = await mountMenu();

    await wrapper.find('a[href="/explorer/notify"]').trigger("click");

    expect(useSidebar().open.value).toBe(false);
  });
});
