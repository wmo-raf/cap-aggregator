import { severityColor, severityRank } from "@/lib/severity";

/** Popup data/content for alert clicks. Pure DOM construction (no innerHTML
 * with tile data — property values are untrusted upstream content). */

export interface PopupAlert {
  id: number;
  chain: number;
  event: string;
  headline: string;
  severity: string;
  authority: string;
  expires: string | null;
}

/** queryRenderedFeatures returns one feature per tile segment — dedupe by
 * alert id and order the overlap stack worst-severity first. */
export function dedupeAlertFeatures(features: { properties: Record<string, unknown> }[]): PopupAlert[] {
  const byId = new Map<number, PopupAlert>();
  for (const f of features) {
    const p = f.properties;
    const id = Number(p.id);
    if (!byId.has(id)) {
      byId.set(id, {
        id,
        chain: Number(p.chain),
        event: String(p.event ?? ""),
        headline: String(p.headline ?? ""),
        severity: String(p.severity ?? ""),
        authority: String(p.authority ?? ""),
        expires: typeof p.expires === "string" ? p.expires : null,
      });
    }
  }
  return [...byId.values()].sort((a, b) => severityRank(a.severity) - severityRank(b.severity));
}

export function buildPopupContent(alerts: PopupAlert[]): HTMLElement {
  const root = document.createElement("div");
  root.className = "capagg-popup";

  for (const alert of alerts) {
    const item = document.createElement("a");
    item.href = `/alerts/${alert.chain}/`;
    item.className = "capagg-popup__item";

    const title = document.createElement("span");
    title.className = "capagg-popup__title";
    const dot = document.createElement("span");
    dot.className = "capagg-popup__dot";
    dot.style.backgroundColor = severityColor(alert.severity);
    dot.title = alert.severity;
    title.append(dot, document.createTextNode(alert.headline || alert.event));

    const meta = document.createElement("span");
    meta.className = "capagg-popup__meta";
    const expiry = alert.expires ? ` · until ${new Date(alert.expires).toLocaleString()}` : "";
    meta.textContent = `${alert.event} · ${alert.authority}${expiry}`;

    item.append(title, meta);
    root.append(item);
  }
  return root;
}
