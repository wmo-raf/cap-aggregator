import type { ExpressionSpecification } from "maplibre-gl";

/**
 * MeteoAlarm severity convention — the single source of truth for both the
 * map layer styling and the legend. Values mirror the --color-severity-*
 * design tokens in assets/main.css.
 */
export const SEVERITIES = [
  { value: "extreme", label: "Extreme", color: "#7a0177" },
  { value: "severe", label: "Severe", color: "#e31a1c" },
  { value: "moderate", label: "Moderate", color: "#fd8d3c" },
  { value: "minor", label: "Minor", color: "#fecc5c" },
] as const;

/** Neutral fill for Unknown/absent severities — deliberately not a MeteoAlarm color. */
export const SEVERITY_FALLBACK_COLOR = "#9ca3af";

/** Worst-first rank (0 = Extreme); unknown severities rank after Minor. */
export function severityRank(severity: string): number {
  const index = SEVERITIES.findIndex((s) => s.value === severity.toLowerCase());
  return index === -1 ? SEVERITIES.length : index;
}

/** The severity's MeteoAlarm color, or the neutral fallback. */
export function severityColor(severity: string): string {
  return SEVERITIES.find((s) => s.value === severity.toLowerCase())?.color ?? SEVERITY_FALLBACK_COLOR;
}

/**
 * Data-driven MapLibre color expression over the tile `severity` property.
 * CAP producers vary in casing, so the match is case-insensitive.
 */
export function severityColorExpression(): ExpressionSpecification {
  return [
    "match",
    ["downcase", ["coalesce", ["get", "severity"], ""]],
    ...SEVERITIES.flatMap((s) => [s.value, s.color] as const),
    SEVERITY_FALLBACK_COLOR,
  ] as unknown as ExpressionSpecification;
}
