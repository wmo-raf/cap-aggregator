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
    script.textContent = JSON.stringify({ tilesBase: "http://localhost:3000/tiles" });
    document.body.appendChild(script);

    expect(appConfig().tilesBase).toBe("http://localhost:3000/tiles");
    expect(alertTileUrlTemplate()).toBe("http://localhost:3000/tiles/alerts/{z}/{x}/{y}");
  });

  it("resolves the fallback /tiles base to an absolute URL (maplibre tile workers cannot parse relative URLs)", () => {
    expect(appConfig().tilesBase).toBe(`${window.location.origin}/tiles`);
    expect(alertTileUrlTemplate()).toBe(`${window.location.origin}/tiles/alerts/{z}/{x}/{y}`);
  });

  it("resolves a relative configured base against the page origin, ignoring trailing slashes", () => {
    const script = document.createElement("script");
    script.id = "capagg-config";
    script.type = "application/json";
    script.textContent = JSON.stringify({ tilesBase: "/tiles/" });
    document.body.appendChild(script);

    expect(alertTileUrlTemplate()).toBe(`${window.location.origin}/tiles/alerts/{z}/{x}/{y}`);
  });
});
