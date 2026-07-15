import { describe, expect, it } from "vitest";

import { countryFlagEmoji } from "@/lib/countryFlag";

describe("countryFlagEmoji", () => {
  it("maps ISO2 codes to regional-indicator flags", () => {
    expect(countryFlagEmoji("KE")).toBe("🇰🇪");
    expect(countryFlagEmoji("dz")).toBe("🇩🇿");
  });

  it("returns an empty string for missing or malformed codes", () => {
    expect(countryFlagEmoji("")).toBe("");
    expect(countryFlagEmoji("KEN")).toBe("");
    expect(countryFlagEmoji("K1")).toBe("");
  });
});
