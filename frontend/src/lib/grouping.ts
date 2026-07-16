import { SEVERITIES, SEVERITY_FALLBACK_COLOR } from "@/lib/severity";

/** The table's grouping dimension; `group` URL param (omitted at default). */
export type TableGrouping = "country" | "severity" | "effective";

export const DEFAULT_GROUPING: TableGrouping = "effective";

const GROUPINGS: TableGrouping[] = ["country", "severity", "effective"];

export function groupingFromQuery(query: Record<string, unknown>): TableGrouping {
  const raw = query.group;
  return GROUPINGS.find((g) => g === raw) ?? DEFAULT_GROUPING;
}

export function groupingToQuery(grouping: TableGrouping): Record<string, string> {
  return grouping === DEFAULT_GROUPING ? {} : { group: grouping };
}

export interface AuthorityGroup<T> {
  /** Unique across the table: country code + authority slug. */
  key: string;
  slug: string;
  name: string;
  items: T[];
}

export interface CountryGroup<T> {
  code: string;
  name: string;
  authorities: AuthorityGroup<T>[];
}

interface CountryAuthorityRow {
  authority: string;
  authority_name: string;
  authority_country: string;
  authority_country_name: string;
}

/**
 * Nest items by issuing authority's country, then authority, preserving input
 * order — the search API's order=country keeps groups contiguous across pages.
 */
export function groupByCountryAuthority<T extends CountryAuthorityRow>(items: T[]): CountryGroup<T>[] {
  const countries = new Map<string, CountryGroup<T>>();

  for (const item of items) {
    const country =
      countries.get(item.authority_country) ??
      countries
        .set(item.authority_country, { code: item.authority_country, name: item.authority_country_name, authorities: [] })
        .get(item.authority_country)!;
    const key = `${item.authority_country}/${item.authority}`;
    let authority = country.authorities.find((a) => a.key === key);
    if (!authority) {
      authority = { key, slug: item.authority, name: item.authority_name, items: [] };
      country.authorities.push(authority);
    }
    authority.items.push(item);
  }

  return [...countries.values()];
}

export interface DayGroup<T> {
  /** Zone-local YYYY-MM-DD, or "unknown" for the trailing no-effective group. */
  value: string;
  label: string;
  items: T[];
}

/**
 * Bucket items by the calendar day of their effective time (viewer-local by
 * default), preserving input order — the API's newest-first default keeps
 * day groups contiguous across pages. Items with no effective time stay
 * visible in a trailing "Unknown" group.
 */
export function groupByEffectiveDay<T extends { effective: string | null }>(
  items: T[],
  { locale, timeZone }: { locale?: string; timeZone?: string } = {},
): DayGroup<T>[] {
  const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone, dateStyle: "short" }); // YYYY-MM-DD
  const dayLabel = new Intl.DateTimeFormat(locale, { timeZone, dateStyle: "long" });
  const days = new Map<string, DayGroup<T>>();
  const unknown: DayGroup<T> = { value: "unknown", label: "Unknown", items: [] };

  for (const item of items) {
    if (!item.effective) {
      unknown.items.push(item);
      continue;
    }
    const date = new Date(item.effective);
    const value = dayKey.format(date);
    const group =
      days.get(value) ?? days.set(value, { value, label: dayLabel.format(date), items: [] }).get(value)!;
    group.items.push(item);
  }

  return [...days.values(), ...(unknown.items.length ? [unknown] : [])];
}

export interface SeverityGroup<T> {
  value: string;
  label: string;
  color: string;
  items: T[];
}

/**
 * Group items by severity, worst-first per the MeteoAlarm order; only
 * non-empty groups are returned. Unexpected severity values stay visible as
 * trailing neutral groups (first-seen order) rather than disappearing.
 */
export function groupBySeverity<T extends { severity: string }>(items: T[]): SeverityGroup<T>[] {
  const known = new Map<string, SeverityGroup<T>>(
    SEVERITIES.map((s) => [s.value, { value: s.value, label: s.label, color: s.color, items: [] }]),
  );
  const other = new Map<string, SeverityGroup<T>>();

  for (const item of items) {
    const key = item.severity.toLowerCase();
    const group =
      known.get(key) ??
      other.get(key) ??
      other.set(key, { value: key, label: item.severity, color: SEVERITY_FALLBACK_COLOR, items: [] }).get(key)!;
    group.items.push(item);
  }

  return [...known.values(), ...other.values()].filter((g) => g.items.length > 0);
}
