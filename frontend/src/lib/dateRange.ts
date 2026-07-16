import { type AlertFilters, filtersToRouteQuery } from "@/lib/filters";
import { DEFAULT_GROUPING, type TableGrouping } from "@/lib/grouping";

/** The Table's effective-date range ("issued between") — date-only strings
 * (YYYY-MM-DD); the API treats the end date as inclusive of that whole day. */
export interface DateRange {
  from: string;
  to: string;
}

export const TABLE_PAGE_SIZE = 50;

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** Last 7 days, inclusive of today (== the "7d" preset). */
export function defaultRange(now: Date = new Date()): DateRange {
  return presetRange("7d", now);
}

export type DatePresetKey = "today" | "7d" | "30d" | "90d";

/** The one-click ranges offered by the Date range panel, besides Custom. */
export const DATE_PRESETS: { key: DatePresetKey; label: string; days: number }[] = [
  { key: "today", label: "Today", days: 0 },
  { key: "7d", label: "Last 7 days", days: 7 },
  { key: "30d", label: "Last 30 days", days: 30 },
  { key: "90d", label: "Last 90 days", days: 90 },
];

/** A preset resolved to the absolute range it means right now. */
export function presetRange(key: DatePresetKey, now: Date = new Date()): DateRange {
  const preset = DATE_PRESETS.find((p) => p.key === key)!;
  const from = new Date(now.getTime() - preset.days * 24 * 60 * 60 * 1000);
  return { from: isoDate(from), to: isoDate(now) };
}

/** The preset an absolute range corresponds to today, or null (custom). */
export function matchPreset(range: DateRange, now: Date = new Date()): DatePresetKey | null {
  const match = DATE_PRESETS.find((p) => {
    const resolved = presetRange(p.key, now);
    return resolved.from === range.from && resolved.to === range.to;
  });
  return match?.key ?? null;
}

export function rangeToQuery(range: DateRange): Record<string, string> {
  return { from: range.from, to: range.to };
}

export function rangeFromQuery(query: Record<string, unknown>, now: Date = new Date()): DateRange {
  const from = query.from;
  const to = query.to;
  if (typeof from === "string" && DATE_RE.test(from) && typeof to === "string" && DATE_RE.test(to)) {
    return { from, to };
  }
  return defaultRange(now);
}

/** A YYYY-MM-DD string as a local date — via parts, so no UTC-midnight drift. */
function localDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

/** Compact display of the applied range for the table header, e.g.
 * "9 – 16 Jul 2026"; a single-day range collapses to one date. */
export function formatDateRange(range: DateRange, locale?: string): string {
  const formatter = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric" });
  return range.from === range.to
    ? formatter.format(localDate(range.from))
    : formatter.formatRange(localDate(range.from), localDate(range.to));
}

/** /api/search/ params for the table: range + facets + pagination + the
 * server ordering matching the grouping, so grouped rows stay contiguous
 * across pages ("effective" rides the API's newest-first default). */
export function tableSearchParams(
  filters: AlertFilters,
  range: DateRange,
  offset = 0,
  grouping: TableGrouping = DEFAULT_GROUPING,
): URLSearchParams {
  const params = new URLSearchParams(filtersToRouteQuery(filters));
  params.set("effective_from", range.from);
  params.set("effective_to", range.to);
  params.set("limit", String(TABLE_PAGE_SIZE));
  params.set("offset", String(offset));
  if (grouping !== "effective") params.set("order", grouping);
  return params;
}
