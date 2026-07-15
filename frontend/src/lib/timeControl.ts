/** Time-travel state for the map: tile `t` param handling.
 * Times are floored to 5-minute buckets so identical URLs hit the nginx tile
 * cache; `null` means live mode (no `t` param, tiles default to now()). */

const BUCKET_MS = 5 * 60 * 1000;

export function roundToBucket(date: Date): Date {
  return new Date(Math.floor(date.getTime() / BUCKET_MS) * BUCKET_MS);
}

/** URL query fragment for the selected time ({} in live mode). */
export function timeToQuery(date: Date | null): { t?: string } {
  return date ? { t: roundToBucket(date).toISOString() } : {};
}

/** Parse the `t` query param; invalid or absent → live mode (null). */
export function timeFromQuery(query: Record<string, unknown>): Date | null {
  const raw = query.t;
  if (typeof raw !== "string") return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : roundToBucket(parsed);
}

export function nextStep(date: Date, minutes: number): Date {
  return new Date(date.getTime() + minutes * 60 * 1000);
}
