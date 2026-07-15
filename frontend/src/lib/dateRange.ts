import { type AlertFilters, filtersToRouteQuery } from "@/lib/filters";

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

/** Last 7 days, inclusive of today. */
export function defaultRange(now: Date = new Date()): DateRange {
  const from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  return { from: isoDate(from), to: isoDate(now) };
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

/** /api/search/ params for the table: range + facets + pagination. */
export function tableSearchParams(filters: AlertFilters, range: DateRange, offset = 0): URLSearchParams {
  const params = new URLSearchParams(filtersToRouteQuery(filters));
  params.set("effective_from", range.from);
  params.set("effective_to", range.to);
  params.set("limit", String(TABLE_PAGE_SIZE));
  params.set("offset", String(offset));
  params.set("order", "severity"); // grouped rows stay contiguous across pages
  return params;
}
