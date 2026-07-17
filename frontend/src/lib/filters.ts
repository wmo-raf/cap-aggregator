import type { LocationQuery } from "vue-router";

import { roundToBucket } from "@/lib/timeControl";

/**
 * The map/table facet filter state and its serializations — one source of
 * truth for the three contracts that must stay in lockstep:
 *   route query (deep links) ↔ filters ↔ Martin tile params + search API params.
 * Facet keys mirror the tile function / search API vocabulary (msg_type etc.).
 */
export interface AlertFilters {
  severity: string[];
  urgency: string[];
  certainty: string[];
  category: string[];
  msgType: string[];
  country: string[];
}

/** filter field → wire param name (tile function, search API and URL agree). */
export const FACETS: [keyof AlertFilters, string][] = [
  ["severity", "severity"],
  ["urgency", "urgency"],
  ["certainty", "certainty"],
  ["category", "category"],
  ["msgType", "msg_type"],
  ["country", "country"],
];

/** The wire param names — for stripping facet keys from a URL query. */
export const FACET_PARAMS = FACETS.map(([, param]) => param);

export function emptyFilters(): AlertFilters {
  return { severity: [], urgency: [], certainty: [], category: [], msgType: [], country: [] };
}

export function hasActiveFilters(filters: AlertFilters): boolean {
  return FACETS.some(([field]) => filters[field].length > 0);
}

/** CSV-valued query object for the route URL; empty facets omitted. */
export function filtersToRouteQuery(filters: AlertFilters): Record<string, string> {
  const query: Record<string, string> = {};
  for (const [field, param] of FACETS) {
    if (filters[field].length) query[param] = filters[field].join(",");
  }
  return query;
}

/** Parse a vue-router query (values may repeat as arrays) back into filters. */
export function filtersFromRouteQuery(query: LocationQuery | Record<string, unknown>): AlertFilters {
  const filters = emptyFilters();
  for (const [field, param] of FACETS) {
    const raw = (query as Record<string, unknown>)[param];
    const values = (Array.isArray(raw) ? raw : [raw])
      .filter((v): v is string => typeof v === "string" && v.length > 0)
      .flatMap((v) => v.split(","))
      .filter(Boolean);
    filters[field] = values;
  }
  return filters;
}

/** Martin tile URL query params (the tile function reads them as query_params).
 * Always pins status=Actual: the tile function has no default, and the map must
 * agree with the search API's public default (Exercise/Test never render). */
export function tileQueryFromFilters(filters: AlertFilters): Record<string, string> {
  return { status: "Actual", ...filtersToRouteQuery(filters) };
}

/** /api/search/ params: the facets, the viewport bbox and the selected time. */
export function searchParamsFromFilters(
  filters: AlertFilters,
  bbox: [number, number, number, number] | null,
  time: Date | null = null,
): URLSearchParams {
  const params = new URLSearchParams(filtersToRouteQuery(filters));
  if (bbox) params.set("bbox", bbox.join(","));
  if (time) params.set("t", roundToBucket(time).toISOString());
  return params;
}
