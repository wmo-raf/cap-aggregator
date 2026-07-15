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

  it("falls back to the nginx-proxied /martin base when no config is injected", () => {
    expect(appConfig().tilesBase).toBe("/martin");
    expect(alertTileUrlTemplate()).toBe("/martin/alerts/{z}/{x}/{y}");
  });

  it("ignores a trailing slash on the configured base", () => {
    const script = document.createElement("script");
    script.id = "capagg-config";
    script.type = "application/json";
    script.textContent = JSON.stringify({ tilesBase: "/martin/" });
    document.body.appendChild(script);

    expect(alertTileUrlTemplate()).toBe("/martin/alerts/{z}/{x}/{y}");
  });
});
