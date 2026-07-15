/** CAP v1.2 facet vocabularies (mirroring alerts.models choices). */

export const URGENCIES = ["Immediate", "Expected", "Future", "Past", "Unknown"] as const;
export const CERTAINTIES = ["Observed", "Likely", "Possible", "Unlikely", "Unknown"] as const;
export const MSG_TYPES = ["Alert", "Update", "Cancel"] as const;
export const CATEGORIES = [
  "Geo", "Met", "Safety", "Security", "Rescue", "Fire",
  "Health", "Env", "Transport", "Infra", "CBRNE", "Other",
] as const;
