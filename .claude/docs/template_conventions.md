# Template conventions & styling

Conventions for Django/Wagtail HTML templates. The **markup/JS conventions**
below apply to every template (admin and public frontend); the **CSS custom
property** rules are context-specific (admin vs. frontend). The running example
is the health dashboard panels under `ingestion/templates/capagg_ingestion/`,
which extend `wagtailadmin/base.html`.

## Markup & JS conventions

- **No inline styles** — never use `style="..."` attributes. Extract all CSS into
  a `{% block extra_css %}<style>…</style>{% endblock %}` block and give elements
  semantic class names.
- **Modern JS** — use `const` and `let`; never `var`.
- **JS placement** — all JavaScript goes in `{% block extra_js %}…{% endblock %}`
  at the bottom of the template. Wrap code in
  `document.addEventListener('DOMContentLoaded', function () { … })` rather than
  an IIFE `(function () { … }())`.

## CSS custom properties: which to use

| Context                                                          | Variables     | Where defined                                |
|------------------------------------------------------------------|---------------|----------------------------------------------|
| **Wagtail admin** templates (`extends "wagtailadmin/base.html"`) | `--w-color-*` | Wagtail 7 admin CSS                          |
| **Public frontend** (Vue/MapLibre SPA, non-admin templates)      | `--color-*`   | Our own frontend CSS (project design tokens) |

**Never mix token families.** The two contexts are separate CSS worlds:

- In **admin** templates, use Wagtail 7's `--w-color-*` tokens only. Wagtail 7
  removed the old unprefixed `--color-*` aliases entirely, so a bare `--color-*`
  in an admin template resolves to nothing and falls back to the browser default.
- In the **public frontend**, define and use our own `--color-*` design tokens
  (declared in the frontend's own CSS, per the `extra_css` convention in
  `docs/design.md` §9). Never reference Wagtail's `--w-color-*` tokens here —
  they aren't loaded outside the admin.

## Key `--color-*` frontend tokens

Declared in `frontend/src/assets/main.css` (Tailwind v4 `@theme` — each token is
also a Tailwind utility, e.g. `bg-background`, `text-muted-foreground`). Light
and dark values switch via the `.dark` class on `<html>`; severity colors are
identical in both themes.

- **Surfaces:** `--color-background`, `--color-card`, `--color-popover`
- **Text:** `--color-foreground`, `--color-muted-foreground`, plus per-surface
  `--color-card-foreground`, `--color-popover-foreground`
- **Chrome (neutral slate — deliberately not red):** `--color-primary`,
  `--color-primary-foreground`, `--color-secondary`, `--color-muted`,
  `--color-accent` (+ their `-foreground` pairs)
- **Lines & focus:** `--color-border`, `--color-input`, `--color-ring`
- **Errors:** `--color-destructive`, `--color-destructive-foreground`
- **Brand:** `--color-brand` — the logo red; logo and small accents ONLY, never
  chrome (red must keep its exclusive "Severe" meaning next to alert data)
- **Severity (MeteoAlarm, data displays only):** `--color-severity-extreme`,
  `--color-severity-severe`, `--color-severity-moderate`, `--color-severity-minor`

In Vue SFCs, style with Tailwind utilities backed by these tokens. In
server-rendered public templates, reference the tokens from `extra_css` blocks.

## Key `--w-color-*` tokens

- **Borders:** `--w-color-border-furniture`
- **Muted / secondary text:** `--w-color-grey-400`
- **Subtle backgrounds / panel-header bg:** `--w-color-grey-50`, `--w-color-grey-100`
- **Menus & surfaces:** `--w-color-surface-menus`, `--w-color-surface-field`, `--w-color-surface-page`
- **Labels / primary text:** `--w-color-text-label`
- **White:** `--w-color-white`
- **Status colours:** `--w-color-info-100`, `--w-color-positive-100`, `--w-color-warning-100`, `--w-color-critical-200`
