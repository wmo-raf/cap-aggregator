import { SEVERITIES, SEVERITY_FALLBACK_COLOR } from "@/lib/severity";

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
