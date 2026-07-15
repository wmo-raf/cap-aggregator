import { beforeEach, describe, expect, it } from "vitest";

import { alertTileUrlTemplate, appConfig } from "@/lib/config";

describe("app config", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("reads the tiles base injected by the Django shell", () => {
    const script = document.createElement("script");
    script.id = "capagg-config";
    script.type = "application/json";
    script.textContent = JSON.stringify({ tilesBase: "http://localhost:3000/martin" });
    document.body.appendChild(script);

    expect(appConfig().tilesBase).toBe("http://localhost:3000/martin");
    expect(alertTileUrlTemplate()).toBe("http://localhost:3000/martin/alerts/{z}/{x}/{y}");
  });

  it("resolves the fallback /martin base to an absolute URL (maplibre tile workers cannot parse relative URLs)", () => {
    expect(appConfig().tilesBase).toBe(`${window.location.origin}/martin`);
    expect(alertTileUrlTemplate()).toBe(`${window.location.origin}/martin/alerts/{z}/{x}/{y}`);
  });

  it("resolves a relative configured base against the page origin, ignoring trailing slashes", () => {
    const script = document.createElement("script");
    script.id = "capagg-config";
    script.type = "application/json";
    script.textContent = JSON.stringify({ tilesBase: "/martin/" });
    document.body.appendChild(script);

    expect(alertTileUrlTemplate()).toBe(`${window.location.origin}/martin/alerts/{z}/{x}/{y}`);
  });
});
