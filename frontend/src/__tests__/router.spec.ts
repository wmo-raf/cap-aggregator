import { describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import { routes } from "@/router";

function makeRouter() {
  return createRouter({ history: createMemoryHistory("/explorer/"), routes });
}

describe("explorer router", () => {
  it("redirects the explorer root to the map view", async () => {
    const router = makeRouter();
    await router.push("/");
    expect(router.currentRoute.value.name).toBe("map");
  });

  it.each([
    ["/map", "map"],
    ["/table", "table"],
    ["/authorities", "authorities"],
    ["/notify", "notify"],
  ])("resolves %s to the %s view", async (path, name) => {
    const router = makeRouter();
    await router.push(path);
    expect(router.currentRoute.value.name).toBe(name);
  });

  it("falls back to the map view for unknown paths", async () => {
    const router = makeRouter();
    await router.push("/does-not-exist/at-all");
    expect(router.currentRoute.value.name).toBe("map");
  });
});
