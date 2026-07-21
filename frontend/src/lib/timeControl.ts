/** Time-travel state for the map: tile `t` param handling.
 * Times are floored to 5-minute buckets so identical URLs hit the nginx tile
 * cache; `null` means live mode (the route query carries no `t`). */

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

/** The instant a tile request asks for — live mode included.
 *
 * Live mode must NOT fall back to the tile function's own now(): a `t`-less URL
 * is byte-identical forever, so every cache in front of Martin (its 256 MB
 * in-memory tile cache has no TTL at all) pins one render of "now" until
 * eviction — expired alerts stayed on the map for days while the server-rendered
 * list was correct. Bucketing means the URL rotates every 5 minutes, so each
 * cache entry is a snapshot of a fixed instant and ages out on its own. */
export function tileTime(selected: Date | null, now: Date = new Date()): string {
  return roundToBucket(selected ?? now).toISOString();
}

/** Call `onRoll` when the 5-minute bucket rolls over, so a live map left open
 * re-requests tiles instead of showing its first render forever. Returns an
 * unsubscribe. */
export function watchBucket(onRoll: () => void, intervalMs = 15_000): () => void {
  let current = roundToBucket(new Date()).getTime();
  const timer = setInterval(() => {
    const next = roundToBucket(new Date()).getTime();
    if (next !== current) {
      current = next;
      onRoll();
    }
  }, intervalMs);
  return () => clearInterval(timer);
}

export function nextStep(date: Date, minutes: number): Date {
  return new Date(date.getTime() + minutes * 60 * 1000);
}
