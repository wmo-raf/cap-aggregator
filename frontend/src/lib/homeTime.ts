/**
 * Homepage time selector: data-driven buttons derived from the alert list's
 * data-effective/data-expires attributes, in the viewer's timezone.
 *   Now (always, t = null = live) · +24h (if active then) · one button per
 *   day 2-7 at local noon (only days with activity) · Future (first alert
 *   starting beyond 7 days).
 */

export interface TimeWindow {
  effective: string | null;
  expires: string | null;
}

export interface TimeButton {
  key: string;
  label: string;
  t: Date | null;
}

/** Active at instant t; a missing effective means already started, a missing
 * expires means unbounded. */
export function activeAt(window: TimeWindow, t: Date): boolean {
  const started = !window.effective || Date.parse(window.effective) <= t.getTime();
  const alive = !window.expires || t.getTime() < Date.parse(window.expires);
  return started && alive;
}

const HOUR = 3_600_000;

export function deriveTimeButtons(windows: TimeWindow[], now: Date, locale?: string): TimeButton[] {
  const buttons: TimeButton[] = [{ key: "now", label: "Now", t: null }];
  const anyActiveAt = (t: Date) => windows.some((w) => activeAt(w, t));

  const in24h = new Date(now.getTime() + 24 * HOUR);
  if (anyActiveAt(in24h)) buttons.push({ key: "24h", label: "+24h", t: in24h });

  const weekday = new Intl.DateTimeFormat(locale, { weekday: "short" });
  for (let day = 2; day <= 7; day++) {
    const noon = new Date(now.getFullYear(), now.getMonth(), now.getDate() + day, 12);
    if (anyActiveAt(noon)) buttons.push({ key: `day-${day}`, label: weekday.format(noon), t: noon });
  }

  const horizon = now.getTime() + 7 * 24 * HOUR;
  const firstFarStart = windows
    .map((w) => (w.effective ? Date.parse(w.effective) : Number.NaN))
    .filter((ms) => ms > horizon)
    .sort((a, b) => a - b)[0];
  if (firstFarStart) buttons.push({ key: "future", label: "Future", t: new Date(firstFarStart) });

  return buttons;
}
