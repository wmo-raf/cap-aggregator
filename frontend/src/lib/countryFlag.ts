/** ISO-3166 alpha-2 code → regional-indicator flag emoji ("" if malformed). */
export function countryFlagEmoji(code: string): string {
  if (!/^[a-zA-Z]{2}$/.test(code)) return "";
  return [...code.toUpperCase()]
    .map((c) => String.fromCodePoint(0x1f1e6 + c.charCodeAt(0) - 65))
    .join("");
}
