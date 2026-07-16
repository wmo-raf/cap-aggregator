import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter, type Router } from "vue-router";

import { routes } from "@/router";
import TableView from "@/views/TableView.vue";

async function mountView(path = "/table") {
  const router: Router = createRouter({ history: createMemoryHistory("/explorer/"), routes });
  await router.push(path);
  await router.isReady();
  return { wrapper: mount(TableView, { global: { plugins: [router] } }), router };
}

function feature(id: number, overrides: Record<string, unknown> = {}) {
  return {
    id,
    properties: {
      chain: id,
      event: "Flood Warning",
      headline: `Alert ${id}`,
      severity: "Severe",
      authority: "kenya-met",
      authority_name: "Kenya Met Department",
      authority_country: "KE",
      authority_country_name: "Kenya",
      countries: ["ke"],
      status: "Actual",
      msg_type: "Alert",
      effective: "2026-07-16T09:00:00Z",
      expires: "2026-07-17T09:00:00Z",
      is_cancelled: false,
      ...overrides,
    },
  };
}

function stubFetch(features: unknown[], total = features.length) {
  const fetchMock = vi.fn((input: unknown) => {
    const url = String(input);
    const payload = url.startsWith("/api/authorities/")
      ? { results: [], next: null }
      : { count: total, results: { features } };
    return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("TableView", () => {
  it("always shows the total for the current view, even under one page", async () => {
    stubFetch([feature(1), feature(2)], 120);

    const { wrapper } = await mountView();
    await flushPromises();

    expect(wrapper.find('[data-testid="table-total"]').text()).toContain("120 alerts");
  });

  it("shows a table skeleton while loading, replaced by rows when ready", async () => {
    let resolveSearch!: (payload: unknown) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: unknown) => {
        if (String(input).startsWith("/api/authorities/")) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ results: [], next: null }) });
        }
        return new Promise((resolve) => {
          resolveSearch = (payload) => resolve({ ok: true, json: () => Promise.resolve(payload) });
        });
      }),
    );

    const { wrapper } = await mountView();
    await flushPromises();
    expect(wrapper.find('[data-testid="table-skeleton"]').exists()).toBe(true);

    resolveSearch({ count: 1, results: { features: [feature(1)] } });
    await flushPromises();
    expect(wrapper.find('[data-testid="table-skeleton"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("Alert 1");
  });

  it("groups by country then authority when selected, without counts on headers", async () => {
    const fetchMock = stubFetch([
      feature(1),
      feature(2, {
        authority: "uganda-met",
        authority_name: "Uganda Met Authority",
        authority_country: "UG",
        authority_country_name: "Uganda",
      }),
    ]);

    const { wrapper } = await mountView("/table?group=country");
    await flushPromises();

    const searchUrl = String(
      fetchMock.mock.calls.map((c) => String(c[0])).find((url) => url.startsWith("/api/search/")),
    );
    expect(searchUrl).toContain("order=country");

    const countryHeaders = wrapper.findAll('[data-testid="group-header"][data-level="0"]');
    expect(countryHeaders.map((h) => h.text())).toEqual(["🇰🇪 Kenya", "🇺🇬 Uganda"]);

    const authorityHeaders = wrapper.findAll('[data-testid="group-header"][data-level="1"]');
    expect(authorityHeaders.map((h) => h.text())).toEqual(["Kenya Met Department", "Uganda Met Authority"]);
  });

  it("collapses a country group, hiding its authorities and alerts", async () => {
    stubFetch([feature(1), feature(2)]);

    const { wrapper } = await mountView("/table?group=country");
    await flushPromises();

    const kenya = wrapper.find('[data-testid="group-header"][data-level="0"] button');
    expect(kenya.attributes("aria-expanded")).toBe("true");

    await kenya.trigger("click");

    expect(kenya.attributes("aria-expanded")).toBe("false");
    expect(wrapper.findAll('[data-testid="group-header"][data-level="1"]')).toHaveLength(0);
    expect(wrapper.text()).not.toContain("Alert 1");
  });

  it("switches grouping via the toolbar, syncing the URL and refetching", async () => {
    const fetchMock = stubFetch([feature(1)]);

    const { wrapper, router } = await mountView();
    await flushPromises();

    await wrapper.find('[data-testid="grouping-select"]').setValue("severity");
    await flushPromises();

    expect(router.currentRoute.value.query.group).toBe("severity");
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls.some((url) => url.includes("order=severity"))).toBe(true);
    const headers = wrapper.findAll('[data-testid="group-header"][data-level="0"]');
    expect(headers.map((h) => h.text())).toEqual(["Severe"]);
  });

  it("shows the applied date range in a header bar with the total and grouping control", async () => {
    stubFetch([feature(1)]);

    const { wrapper } = await mountView("/table?from=2026-06-01&to=2026-06-30");
    await flushPromises();

    const header = wrapper.find('[data-testid="table-header"]');
    expect(header.exists()).toBe(true);
    expect(header.find('[data-testid="table-total"]').text()).toContain("1 alert");
    expect(header.find('[data-testid="grouping-select"]').exists()).toBe(true);

    const rangeLabel = header.find('[data-testid="table-range"]').text();
    expect(rangeLabel).toContain("Jun");
    expect(rangeLabel).toContain("2026");
    expect(rangeLabel).toContain("30");
  });

  it("keeps the header bar visible when loading fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) })),
    );

    const { wrapper } = await mountView();
    await flushPromises();

    expect(wrapper.find('[data-testid="table-header"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="table-total"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("Could not load alerts");
  });

  it("checks the matching date preset on load and hides the custom pickers", async () => {
    stubFetch([feature(1)]);

    const { wrapper } = await mountView(); // default range == last 7 days
    await flushPromises();

    expect((wrapper.find('[data-testid="range-preset-7d"]').element as HTMLInputElement).checked).toBe(true);
    expect(wrapper.find('[data-testid="range-from"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="range-to"]').exists()).toBe(false);
  });

  it("resolves a clicked preset to absolute from/to in the URL and refetches", async () => {
    const fetchMock = stubFetch([feature(1)]);
    const todayIso = new Date().toISOString().slice(0, 10);

    const { wrapper, router } = await mountView();
    await flushPromises();

    await wrapper.find('[data-testid="range-preset-today"]').setValue(true);
    await flushPromises();

    expect(router.currentRoute.value.query.from).toBe(todayIso);
    expect(router.currentRoute.value.query.to).toBe(todayIso);
    const lastSearch = fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.startsWith("/api/search/")).at(-1)!;
    expect(lastSearch).toContain(`effective_from=${todayIso}`);
    expect(lastSearch).toContain(`effective_to=${todayIso}`);
  });

  it("opens a non-preset deep link as Custom with the pickers prefilled", async () => {
    stubFetch([feature(1)]);

    const { wrapper } = await mountView("/table?from=2026-06-01&to=2026-06-30");
    await flushPromises();

    expect((wrapper.find('[data-testid="range-preset-custom"]').element as HTMLInputElement).checked).toBe(true);
    expect((wrapper.find('[data-testid="range-from"]').element as HTMLInputElement).value).toBe("2026-06-01");
    expect((wrapper.find('[data-testid="range-to"]').element as HTMLInputElement).value).toBe("2026-06-30");
  });

  it("switching to Custom reveals the pickers without refetching until a date is edited", async () => {
    const fetchMock = stubFetch([feature(1)]);

    const { wrapper } = await mountView();
    await flushPromises();
    const searchCalls = () => fetchMock.mock.calls.filter((c) => String(c[0]).startsWith("/api/search/")).length;
    const before = searchCalls();

    await wrapper.find('[data-testid="range-preset-custom"]').setValue(true);
    await flushPromises();

    expect(wrapper.find('[data-testid="range-from"]').exists()).toBe(true);
    expect(searchCalls()).toBe(before); // no reload from merely revealing the pickers

    await wrapper.find('[data-testid="range-from"]').setValue("2026-07-01");
    await flushPromises();
    expect(searchCalls()).toBe(before + 1);
  });

  it("groups by effective calendar day by default", async () => {
    stubFetch([feature(1)]);

    const { wrapper, router } = await mountView();
    await flushPromises();

    const select = wrapper.find('[data-testid="grouping-select"]');
    expect((select.element as HTMLSelectElement).value).toBe("effective");
    expect(router.currentRoute.value.query.group).toBeUndefined(); // default stays out of the URL
    const headers = wrapper.findAll('[data-testid="group-header"]');
    expect(headers).toHaveLength(1);
    expect(headers[0].text()).toContain("2026"); // the effective calendar day
  });
});
