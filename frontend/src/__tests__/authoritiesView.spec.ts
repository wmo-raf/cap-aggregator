import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import { routes } from "@/router";
import AuthoritiesView from "@/views/AuthoritiesView.vue";

async function mountView() {
  const router = createRouter({ history: createMemoryHistory("/explorer/"), routes });
  await router.push("/authorities");
  await router.isReady();
  return mount(AuthoritiesView, { global: { plugins: [router] } });
}

const KENYA = {
  name: "Kenya Met",
  slug: "kenya-met",
  country: "KE",
  country_name: "Kenya",
  website: "https://meteo.go.ke",
  active_alert_count: 3,
};
const QUIET = {
  name: "Uganda Met",
  slug: "uganda-met",
  country: "UG",
  country_name: "Uganda",
  website: "",
  active_alert_count: 0,
};

function stubFetch(payload: unknown, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    json: () => Promise.resolve(payload),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("AuthoritiesView", () => {
  it("lists authorities from /api/authorities/ with flag, count and website link", async () => {
    const fetchMock = stubFetch({ results: [KENYA, QUIET], next: null });

    const wrapper = await mountView();
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledWith("/api/authorities/", expect.anything());
    expect(wrapper.text()).toContain("Kenya Met");
    expect(wrapper.text()).toContain("Uganda Met");
    expect(wrapper.text()).toContain("🇰🇪");
    const link = wrapper.find('a[href="https://meteo.go.ke"]');
    expect(link.exists()).toBe(true);
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toContain("noopener");
  });

  it("shows the active alert count per authority", async () => {
    stubFetch({ results: [KENYA], next: null });

    const wrapper = await mountView();
    await flushPromises();

    expect(wrapper.find("[data-testid='alert-count']").text()).toContain("3");
  });

  it("shows an error state when the API fails", async () => {
    stubFetch({}, false);

    const wrapper = await mountView();
    await flushPromises();

    expect(wrapper.text().toLowerCase()).toContain("could not load");
  });
});
