import type { Authority } from "@/lib/api";

/** Sidebar state for the Authorities view — URL is the source of truth,
 * defaults (flat, all authorities) are omitted from the query. */
export interface AuthoritiesState {
  activeOnly: boolean;
  group: "flat" | "country";
}

export function stateFromQuery(query: Record<string, unknown>): AuthoritiesState {
  return {
    activeOnly: query.active === "1",
    group: query.group === "country" ? "country" : "flat",
  };
}

export function stateToQuery(state: AuthoritiesState): Record<string, string> {
  const query: Record<string, string> = {};
  if (state.activeOnly) query.active = "1";
  if (state.group === "country") query.group = state.group;
  return query;
}

export interface CountryGroup {
  code: string;
  name: string;
  items: Authority[];
}

/** Group authorities by country, countries sorted by display name. */
export function groupByCountry(authorities: Authority[]): CountryGroup[] {
  const groups = new Map<string, CountryGroup>();
  for (const authority of authorities) {
    const group =
      groups.get(authority.country) ??
      groups.set(authority.country, { code: authority.country, name: authority.country_name, items: [] }).get(authority.country)!;
    group.items.push(authority);
  }
  return [...groups.values()].sort((a, b) => a.name.localeCompare(b.name));
}
