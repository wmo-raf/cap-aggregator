import { type DateRange, tableSearchParams } from "@/lib/dateRange";
import { type AlertFilters, searchParamsFromFilters } from "@/lib/filters";
import { DEFAULT_GROUPING, type TableGrouping } from "@/lib/grouping";

export interface Authority {
  name: string;
  slug: string;
  country: string;
  country_name: string;
  website: string;
  active_alert_count: number;
}

interface Page<T> {
  results: T[];
  next: string | null;
}

export interface AlertListItem {
  id: number;
  chain: number;
  event: string;
  headline: string;
  severity: string;
  authority: string;
  expires: string | null;
  is_cancelled: boolean;
}

interface GeoPage {
  count: number;
  results: { features: { id: number; properties: Omit<AlertListItem, "id"> }[] };
}

/** Alerts matching the facet filters within the viewport bbox (first page,
 * newest first — the sidebar is a scan list, not an archive). */
export async function fetchAlertList(
  filters: AlertFilters,
  bbox: [number, number, number, number] | null,
  time: Date | null = null,
): Promise<{ alerts: AlertListItem[]; total: number }> {
  const params = searchParamsFromFilters(filters, bbox, time);
  const response = await fetch(`/api/search/?${params}`, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`alert search failed: ${response.status}`);
  const page = (await response.json()) as GeoPage;
  return {
    total: page.count,
    alerts: page.results.features.map((f) => ({ id: f.id, ...f.properties })),
  };
}

export interface TableAlert extends AlertListItem {
  status: string;
  msg_type: string;
  countries: string[];
  effective: string | null;
  authority_name: string;
  authority_country: string;
  authority_country_name: string;
}

/** One table page of alerts effective within the range, server-ordered to
 * match the active grouping. */
export async function fetchAlertTable(
  filters: AlertFilters,
  range: DateRange,
  offset = 0,
  grouping: TableGrouping = DEFAULT_GROUPING,
): Promise<{ alerts: TableAlert[]; total: number }> {
  const params = tableSearchParams(filters, range, offset, grouping);
  const response = await fetch(`/api/search/?${params}`, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`alert search failed: ${response.status}`);
  const page = (await response.json()) as {
    count: number;
    results: { features: { id: number; properties: Omit<TableAlert, "id"> }[] };
  };
  return {
    total: page.count,
    alerts: page.results.features.map((f) => ({ id: f.id, ...f.properties })),
  };
}

/** Effective/expires windows of all active + upcoming alerts (global, not
 * viewport-scoped) — what the time control derives its Live chips from. */
export async function fetchAlertWindows(): Promise<{ effective: string | null; expires: string | null }[]> {
  const response = await fetch("/api/search/?upcoming=true&limit=500", {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`alert windows request failed: ${response.status}`);
  const page = (await response.json()) as {
    results: { features: { properties: { effective: string | null; expires: string | null } }[] };
  };
  return page.results.features.map((f) => ({
    effective: f.properties.effective,
    expires: f.properties.expires,
  }));
}

/** All active authorities, following DRF pagination if there are many. */
export async function fetchAuthorities(): Promise<Authority[]> {
  const authorities: Authority[] = [];
  let url: string | null = "/api/authorities/";
  while (url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`authorities request failed: ${response.status}`);
    const page = (await response.json()) as Page<Authority>;
    authorities.push(...page.results);
    url = page.next;
  }
  return authorities;
}
